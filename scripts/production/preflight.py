#!/usr/bin/env python3
"""Fail-closed, read-only preflight for a production Compose cutover."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

checks: list[str] = []
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
MIGRATION_PROBE_CODE = '''
from sqlalchemy import text
from cme_api.db import SessionLocal
from cme_api.main import EXPECTED_SCHEMA_REVISION

db = SessionLocal()
try:
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    privileges = db.execute(text("""
        SELECT role.rolcanlogin AND NOT role.rolsuper AND NOT role.rolcreatedb
            AND NOT role.rolcreaterole AND NOT role.rolreplication
            AND NOT role.rolbypassrls
            AND has_schema_privilege(current_user, 'public', 'USAGE')
            AND has_schema_privilege(current_user, 'public', 'CREATE')
            AND NOT EXISTS (
                SELECT 1
                FROM pg_class AS object
                JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
                WHERE namespace.nspname = 'public'
                    AND object.relkind IN ('r', 'p', 'S', 'v', 'm')
                    AND NOT (
                        object.relowner = role.oid
                        OR pg_has_role(role.oid, object.relowner, 'USAGE')
                    )
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_type AS object
                JOIN pg_namespace AS namespace ON namespace.oid = object.typnamespace
                WHERE namespace.nspname = 'public'
                    AND object.typtype IN ('d', 'e')
                    AND NOT (
                        object.typowner = role.oid
                        OR pg_has_role(role.oid, object.typowner, 'USAGE')
                    )
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_proc AS object
                JOIN pg_namespace AS namespace ON namespace.oid = object.pronamespace
                WHERE namespace.nspname = 'public'
                    AND NOT (
                        object.proowner = role.oid
                        OR pg_has_role(role.oid, object.proowner, 'USAGE')
                    )
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_roles AS granted_role
                WHERE (
                    granted_role.rolsuper OR granted_role.rolcreatedb
                    OR granted_role.rolcreaterole OR granted_role.rolreplication
                    OR granted_role.rolbypassrls
                )
                    AND pg_has_role(role.oid, granted_role.oid, 'MEMBER')
            )
        FROM pg_roles AS role
        WHERE role.rolname = current_user
    """)).scalar_one()
    assert revision == EXPECTED_SCHEMA_REVISION and privileges
finally:
    db.close()
'''


def report(state: str, name: str, detail: str) -> None:
    checks.append(state)
    print(f"{state} - {name}: {detail}")


def run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    for env_file in os.environ.get("CME_COMPOSE_ENV_FILES", "").split(os.pathsep):
        if env_file:
            command.extend(["--env-file", env_file])
    return [*command, *arguments]


def compose_config_command() -> list[str]:
    # Include the migration service, which is intentionally behind the ops profile.
    return compose_command("--profile", "ops", "config", "--format", "json")


def migration_probe_command() -> list[str]:
    return compose_command(
        "--profile",
        "ops",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "migrate",
        "python",
        "-c",
        MIGRATION_PROBE_CODE,
    )


def connection_identity(value: object) -> tuple[str, str, int, str] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        username = unquote(parsed.username or "", errors="strict")
        hostname = parsed.hostname or ""
        port = parsed.port or 5432
        database = unquote(parsed.path.strip("/"), errors="strict")
        if (
            parsed.scheme not in {"postgresql", "postgresql+psycopg"}
            or INVALID_PERCENT_ESCAPE.search(value)
            or not username
            or not hostname
            or not database
            or parsed.fragment
        ):
            return None
        return username, hostname.casefold().rstrip("."), port, database
    except (ValueError, TypeError, UnicodeError):
        return None


def separate_roles_for_same_database(
    runtime: tuple[str, str, int, str] | None,
    migration: tuple[str, str, int, str] | None,
) -> bool:
    return bool(
        runtime and migration and runtime[0] != migration[0] and runtime[1:] == migration[1:]
    )


def strong_secret(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    categories = sum(
        (
            any(char.islower() for char in value),
            any(char.isupper() for char in value),
            any(char.isdigit() for char in value),
            any(not char.isalnum() for char in value),
        )
    )
    return (
        len(value) >= 24
        and categories >= 3
        and not any(
            marker in lowered for marker in ("change_me", "changeme", "example", "replace_me")
        )
        and lowered not in {"cme", "password", "postgres", "secret"}
    )


def policy_target_configured(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(normalized) and not any(
        marker in normalized
        for marker in (
            "replace_me",
            "changeme",
            "change_me",
            "example",
            "your_",
            "owner_approved",
            "placeholder",
            "todo",
            "tbd",
        )
    )


def verify_backup() -> tuple[str, str]:
    backup_value = os.environ.get("CME_BACKUP_FILE")
    if not backup_value:
        return "BLOCKED", "CME_BACKUP_FILE is not set"
    backup = Path(backup_value)
    checksum = Path(f"{backup}.sha256")
    if (
        backup.is_symlink()
        or checksum.is_symlink()
        or not backup.is_file()
        or not checksum.is_file()
    ):
        return "BLOCKED", "a protected backup and checksum are not available"
    try:
        expected = checksum.read_text(encoding="ascii").strip()
        if len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
            return "FAIL", "backup checksum format is invalid"
        digest = hashlib.sha256()
        with backup.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
    except OSError:
        return "BLOCKED", "backup files cannot be read"
    if actual.casefold() != expected.casefold():
        return "FAIL", "backup checksum does not match"
    if shutil.which("pg_restore") is None:
        return "BLOCKED", "pg_restore is not installed"
    validation = run(["pg_restore", "--list", str(backup)])
    if validation.returncode != 0:
        return "FAIL", "backup archive format could not be validated"
    return "PASS", "backup checksum and archive format are valid"


def main() -> int:
    if shutil.which("docker") is None:
        report("BLOCKED", "Compose configuration", "Docker CLI is unavailable")
        return 2

    config = run(compose_config_command())
    if config.returncode != 0:
        report(
            "BLOCKED",
            "Compose configuration",
            "Docker Compose could not resolve deployment configuration",
        )
        return 2
    try:
        document = json.loads(config.stdout)
    except json.JSONDecodeError:
        report(
            "FAIL",
            "Compose configuration",
            "Docker Compose returned invalid structured configuration",
        )
        return 1
    report("PASS", "Compose configuration", "resolved without printing environment values")

    services = document.get("services", {})
    api = services.get("api", {})
    migrate = services.get("migrate", {})
    api_env = api.get("environment") or {}
    migrate_env = migrate.get("environment") or {}
    postgres_env = services.get("postgres", {}).get("environment") or {}

    app_env = str(api_env.get("CME_APP_ENV", ""))
    if app_env == "production":
        report(
            "PASS",
            "Explicit production environment",
            "API environment selects production",
        )
    else:
        report(
            "FAIL",
            "Explicit production environment",
            "API environment must be production",
        )

    release_sha = str(api.get("build", {}).get("args", {}).get("CME_RELEASE_SHA", ""))
    if SHA_PATTERN.fullmatch(release_sha):
        report(
            "PASS",
            "Release source identity",
            "API image build is pinned to a full Git commit SHA",
        )
    else:
        report(
            "FAIL",
            "Release source identity",
            "set CME_RELEASE_SHA to the full 40-character commit SHA",
        )

    image_ref = str(api.get("image", ""))
    image_digest = re.fullmatch(r".+@sha256:[0-9a-f]{64}", image_ref, re.IGNORECASE)
    image_sha_tag = bool(
        release_sha and image_ref.rsplit(":", 1)[-1].casefold() == release_sha.casefold()
    )
    if image_digest or image_sha_tag:
        report(
            "PASS",
            "Immutable candidate image reference",
            "image uses a SHA-pinned digest or full commit tag",
        )
    else:
        report(
            "FAIL",
            "Immutable candidate image reference",
            "use an image digest or an image tag equal to the full Git SHA",
        )

    postgres_password = postgres_env.get("POSTGRES_PASSWORD")
    if strong_secret(postgres_password):
        report(
            "PASS",
            "PostgreSQL bootstrap secret",
            "PostgreSQL secret is present and meets production strength policy",
        )
    else:
        report(
            "FAIL",
            "PostgreSQL bootstrap secret",
            "replace the development or weak PostgreSQL password",
        )

    api_ports = api.get("ports") or []
    private_api = bool(api_ports) and all(port.get("host_ip") == "127.0.0.1" for port in api_ports)
    if private_api:
        report("PASS", "Private API binding", "all published API ports bind to loopback")
    else:
        report("FAIL", "Private API binding", "API ports must bind only to 127.0.0.1")

    private_dependencies = all(
        not (services.get(name, {}).get("ports") or []) for name in ("postgres", "redis")
    )
    if private_dependencies:
        report(
            "PASS",
            "Database and Redis exposure",
            "neither service publishes a host port",
        )
    else:
        report(
            "FAIL",
            "Database and Redis exposure",
            "PostgreSQL and Redis must remain internal",
        )

    runtime_identity = connection_identity(api_env.get("CME_DATABASE_URL"))
    migration_identity = connection_identity(migrate_env.get("CME_DATABASE_URL"))
    if separate_roles_for_same_database(runtime_identity, migration_identity):
        report(
            "PASS",
            "Runtime and migration identities",
            "application and migration roles differ and target the same database",
        )
    else:
        report(
            "FAIL",
            "Runtime and migration identities",
            "configure distinct application and migration roles for the same valid database",
        )

    settings_probe = run(
        compose_command(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "api",
            "python",
            "-c",
            "from cme_api.config import get_settings; get_settings()",
        )
    )
    if settings_probe.returncode == 0:
        report(
            "PASS",
            "Production settings",
            "database and Redis settings passed application validation",
        )
    elif (
        "ValidationError" in settings_probe.stderr or "production requires" in settings_probe.stderr
    ):
        report(
            "FAIL",
            "Production settings",
            "application validation rejected production settings",
        )
    else:
        report(
            "BLOCKED",
            "Production settings",
            "candidate API image could not be run for validation",
        )

    migration_probe = run(migration_probe_command())
    if migration_probe.returncode == 0:
        report(
            "PASS",
            "Migration role privileges",
            "migration role connects, sees the current revision, owns schema objects, and has no elevated cluster privileges",
        )
    else:
        report(
            "FAIL",
            "Migration role privileges",
            "migration role must connect to the current schema, own or inherit ownership of its objects, and remain non-superuser",
        )

    runtime_probe = run(
        compose_command(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "api",
            "python",
            "-c",
            (
                "from sqlalchemy import text; from cme_api.db import SessionLocal; "
                "from cme_api.main import EXPECTED_SCHEMA_REVISION, _new_redis_client; "
                "db=SessionLocal(); revision=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one(); "
                "privileged=db.execute(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user')).scalar_one(); "
                "db.close(); client=_new_redis_client(); client.ping(); client.close(); "
                "assert revision == EXPECTED_SCHEMA_REVISION and not privileged"
            ),
        )
    )
    if runtime_probe.returncode == 0:
        report(
            "PASS",
            "Database and Redis preflight",
            "schema is current, runtime role has no elevated cluster privileges, Redis answered PING",
        )
    elif not services.get("postgres") or not services.get("redis"):
        report(
            "BLOCKED",
            "Database and Redis preflight",
            "PostgreSQL or Redis service definition is missing",
        )
    else:
        report(
            "BLOCKED",
            "Database and Redis preflight",
            "database or Redis is unavailable to the candidate API container",
        )

    backup_state, backup_detail = verify_backup()
    report(backup_state, "Pre-cutover backup", backup_detail)

    rpo_target = os.environ.get("CME_RPO_TARGET", "").strip()
    rto_target = os.environ.get("CME_RTO_TARGET", "").strip()
    report(
        "PASS" if policy_target_configured(rpo_target) else "BLOCKED",
        "Configured RPO policy",
        "non-placeholder target is configured; release-owner approval is external"
        if policy_target_configured(rpo_target)
        else "release owner must define CME_RPO_TARGET",
    )
    report(
        "PASS" if policy_target_configured(rto_target) else "BLOCKED",
        "Configured RTO policy",
        "non-placeholder target is configured; release-owner approval is external"
        if policy_target_configured(rto_target)
        else "release owner must define CME_RTO_TARGET",
    )

    if all(state == "PASS" for state in checks):
        print("OVERALL - PASS")
        return 0
    print("OVERALL - BLOCKED" if "BLOCKED" in checks else "OVERALL - FAIL")
    return 2 if "BLOCKED" in checks else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        print(
            "BLOCKED - Production preflight: a required local command or dependency is unavailable"
        )
        raise SystemExit(2) from None
