#!/usr/bin/env python3
"""Read-only verification for an isolated CMe PostgreSQL restore target."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from cme_api.db import SessionLocal
from cme_api.main import EXPECTED_SCHEMA_REVISION, app

REQUIRED_TABLES = {
    "alembic_version",
    "audit_events",
    "auth_sessions",
    "chart_accounts",
    "inventory_movements",
    "journal_entries",
    "journal_lines",
    "organizations",
    "tenants",
    "users",
}
REQUIRED_INDEXES = {
    "ix_audit_events_tenant_id",
    "ix_auth_sessions_expires_at",
    "ix_auth_sessions_tenant_user",
    "ix_inventory_movements_sku",
    "ix_inventory_movements_tenant_id",
    "ix_organizations_tenant_id",
    "ix_users_tenant_id",
}
REQUIRED_CONSTRAINTS = {
    "ck_journal_lines_nonnegative",
    "ck_journal_lines_one_sided",
    "fk_audit_events_actor",
    "fk_auth_sessions_user",
    "fk_audit_events_tenant",
    "fk_chart_accounts_organization",
    "fk_inventory_movements_tenant",
    "fk_journal_entries_organization",
    "fk_journal_lines_account",
    "fk_journal_lines_entry",
    "fk_organizations_tenant",
    "fk_users_tenant",
    "uq_chart_accounts_scope",
    "uq_journal_entries_idempotency",
    "uq_journal_entries_scope",
    "uq_tenants_id",
    "uq_users_tenant_id_id",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def verify_client_server_compatibility(server_version_num: int) -> None:
    result = subprocess.run(
        ["pg_restore", "--version"], capture_output=True, text=True, check=False
    )
    match = re.search(r"PostgreSQL\)\s+(\d+)", result.stdout)
    if result.returncode != 0 or match is None:
        fail("pg_restore version could not be determined")
    server_major = server_version_num // 10000
    restore_major = int(match.group(1))
    if server_major != restore_major:
        fail("PostgreSQL server and restore client major versions differ")


def main() -> int:
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != EXPECTED_SCHEMA_REVISION:
            fail("restored schema revision does not match the application")

        server_version_num = int(db.execute(text("SHOW server_version_num")).scalar_one())
        verify_client_server_compatibility(server_version_num)

        inspector = inspect(db.connection())
        tables = set(inspector.get_table_names(schema="public"))
        missing_tables = REQUIRED_TABLES - tables
        if missing_tables or tables != REQUIRED_TABLES:
            fail("restored schema does not match the expected application table set")

        indexes = {
            index["name"]
            for table in REQUIRED_TABLES - {"alembic_version"}
            for index in inspector.get_indexes(table, schema="public")
            if index.get("name")
        }
        if REQUIRED_INDEXES - indexes:
            fail("restored schema is missing required indexes")

        constraints = {
            item.get("name")
            for table in REQUIRED_TABLES - {"alembic_version"}
            for method in (
                inspector.get_check_constraints,
                inspector.get_foreign_keys,
                inspector.get_unique_constraints,
            )
            for item in method(table, schema="public")
            if item.get("name")
        }
        if REQUIRED_CONSTRAINTS - constraints:
            fail("restored schema is missing required constraints")

        unbalanced_entries = db.execute(
            text(
                "SELECT count(*) FROM ("
                "SELECT e.tenant_id, e.organization_id, e.id "
                "FROM journal_entries AS e "
                "JOIN journal_lines AS l "
                "ON l.tenant_id = e.tenant_id "
                "AND l.organization_id = e.organization_id "
                "AND l.entry_id = e.id "
                "WHERE e.posted_at IS NOT NULL "
                "GROUP BY e.tenant_id, e.organization_id, e.id "
                "HAVING sum(l.debit) <> sum(l.credit)"
                ") AS invalid_entries"
            )
        ).scalar_one()
        if unbalanced_entries:
            fail("restored data contains unbalanced posted journal entries")

        row_counts = {
            table: db.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            for table in (
                "tenants",
                "users",
                "audit_events",
                "journal_entries",
                "journal_lines",
            )
        }

    with TestClient(app) as client:
        response = client.get("/ready")
    if response.status_code != 200 or response.json().get("schema_revision") != revision:
        fail("application read-only readiness smoke test failed against restored database")

    print(
        json.dumps(
            {
                "result": "PASS",
                "schema_revision": revision,
                "postgresql_major": server_version_num // 10000,
                "base_tables": len(tables),
                "verified_indexes": len(REQUIRED_INDEXES),
                "verified_constraints": len(REQUIRED_CONSTRAINTS),
                "unbalanced_posted_journal_entries": 0,
                "read_only_row_counts": row_counts,
                "application_readiness": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except (SQLAlchemyError, OSError):
        print(
            "FAIL: database verification failed; connection details were suppressed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
