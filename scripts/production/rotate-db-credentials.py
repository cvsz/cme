#!/usr/bin/env python3
"""Stage a new least-privilege PostgreSQL runtime role without revoking the old role."""

from __future__ import annotations

import os
import re
import secrets
import stat
import sys
from pathlib import Path
from urllib.parse import SplitResult, quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
APPROVAL_VALUE = "I_APPROVE_LIVE_DATABASE_ROLE_CHANGE"
RUNTIME_TABLE_PRIVILEGES = {
    "alembic_version": ("SELECT",),
    "audit_events": ("SELECT", "INSERT"),
    "auth_sessions": ("SELECT", "INSERT", "UPDATE"),
    "chart_accounts": ("SELECT",),
    "inventory_movements": ("SELECT",),
    "journal_entries": ("SELECT", "INSERT", "UPDATE"),
    "journal_lines": ("SELECT", "INSERT"),
    "organizations": ("SELECT",),
    "tenants": ("SELECT",),
    "users": ("SELECT",),
}


class RotationError(Exception):
    pass


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RotationError(f"{name} is required")
    return value


def administrator_url() -> str:
    url_value = os.environ.get("CME_ROTATION_ADMIN_URL", "").strip()
    file_value = os.environ.get("CME_ROTATION_ADMIN_URL_FILE", "").strip()
    if bool(url_value) == bool(file_value):
        raise RotationError(
            "set exactly one of CME_ROTATION_ADMIN_URL or CME_ROTATION_ADMIN_URL_FILE"
        )
    if url_value:
        return url_value
    path = Path(file_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RotationError("administrator URL file must be an absolute, regular, non-symlink file")
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or file_stat.st_mode & 0o077
        ):
            os.close(descriptor)
            raise RotationError(
                "administrator URL file must be owned by the operator and mode 0600 or stricter"
            )
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            value = stream.read().strip()
    except OSError:
        raise RotationError("administrator URL file cannot be read") from None
    if not value or "\n" in value or "\r" in value:
        raise RotationError("administrator URL file must contain one connection URL")
    return value


def parse_database_url(value: str) -> tuple[str, SplitResult, str, str]:
    try:
        parsed = urlsplit(value)
        username = unquote(parsed.username or "", errors="strict")
        database = unquote(parsed.path.strip("/"), errors="strict")
        _ = parsed.port
        if (
            parsed.scheme not in {"postgresql", "postgresql+psycopg"}
            or INVALID_PERCENT_ESCAPE.search(value)
            or not username
            or not database
            or not parsed.hostname
            or parsed.fragment
        ):
            raise ValueError
        driver_url = urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, ""))
        return driver_url, parsed, username, database
    except (ValueError, TypeError, UnicodeError):
        raise RotationError("database administrator URL is invalid") from None


def build_runtime_url(parsed: SplitResult, role: str, password: str) -> str:
    authority = parsed.netloc.rsplit("@", 1)[-1]
    user_info = f"{quote(role, safe='')}:{quote(password, safe='')}@"
    return urlunsplit(("postgresql+psycopg", user_info + authority, parsed.path, parsed.query, ""))


def validate_output_path(value: str) -> Path:
    output = Path(value)
    if not output.is_absolute() or output.is_symlink():
        raise RotationError("credential output must be an absolute, non-symlink path")
    try:
        parent = output.parent.resolve(strict=True)
    except OSError:
        raise RotationError("credential output directory is unavailable") from None
    if parent == ROOT or ROOT in parent.parents:
        raise RotationError("credential output must be outside the repository")
    return parent / output.name


def write_secret_file(path: Path, url: str) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    stat = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"CME_DATABASE_URL={url}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return stat.st_ino


def remove_own_file(path: Path, inode: int) -> None:
    try:
        if path.stat().st_ino == inode:
            path.unlink()
    except OSError:
        pass


def validate_inputs() -> tuple[str, SplitResult, str, str, str, Path]:
    app_env = required("CME_APP_ENV")
    if app_env not in {"production", "test"}:
        raise RotationError("CME_APP_ENV must be production or test")
    if app_env == "production" and os.environ.get("CME_ROTATION_APPROVAL") != APPROVAL_VALUE:
        raise RotationError("live role staging requires explicit CME_ROTATION_APPROVAL")

    admin_raw = administrator_url()
    admin_url, parsed, admin_user, database_name = parse_database_url(admin_raw)
    if app_env == "test":
        try:
            from ipaddress import ip_address

            loopback = ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = (parsed.hostname or "").casefold() == "localhost"
        if not loopback:
            raise RotationError("test mode is restricted to a loopback PostgreSQL endpoint")

    database = required("CME_ROTATION_CONFIRM_DATABASE")
    if database != database_name:
        raise RotationError("database URL does not match CME_ROTATION_CONFIRM_DATABASE")
    role = required("CME_ROTATION_ROLE")
    migration_role = required("CME_ROTATION_MIGRATION_ROLE")
    if not ROLE_PATTERN.fullmatch(role) or not ROLE_PATTERN.fullmatch(migration_role):
        raise RotationError(
            "runtime and migration role names must use lowercase PostgreSQL identifiers"
        )
    if role == migration_role or role == admin_user:
        raise RotationError("new runtime role must differ from migration and administrator roles")
    output_path = validate_output_path(required("CME_ROTATION_OUTPUT_FILE"))
    return admin_url, parsed, database_name, role, migration_role, output_path


def main() -> int:
    output_path: Path | None = None
    output_inode: int | None = None
    committed = False
    driver_error_types: tuple[type[BaseException], ...] = ()
    try:
        admin_url, parsed, database_name, role, migration_role, output_path = validate_inputs()
        import psycopg
        from psycopg import sql

        driver_error_types = (psycopg.Error,)
        with psycopg.connect(admin_url) as admin:
            row = admin.execute(
                "SELECT current_database(), current_user, r.rolsuper, r.rolcreaterole "
                "FROM pg_roles AS r WHERE r.rolname = current_user"
            ).fetchone()
            if row is None or row[0] != database_name:
                raise RotationError("connected database identity could not be verified")
            if not row[2] or not row[3]:
                raise RotationError("role staging requires a PostgreSQL superuser administrator")

            existing = admin.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone()
            if existing:
                raise RotationError(
                    "new runtime role already exists; existing roles are never overwritten"
                )
            migration = admin.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (migration_role,)
            ).fetchone()
            if not migration:
                raise RotationError("configured migration role does not exist")
            tables = {
                table[0]
                for table in admin.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                ).fetchall()
            }
            if tables != set(RUNTIME_TABLE_PRIVILEGES):
                raise RotationError(
                    "public schema table set differs from the reviewed runtime grant policy"
                )

            password = secrets.token_urlsafe(48)
            app_url = build_runtime_url(parsed, role, password)
            output_inode = write_secret_file(output_path, app_url)
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            admin.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name), sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            for table, privileges in RUNTIME_TABLE_PRIVILEGES.items():
                admin.execute(
                    sql.SQL("GRANT {} ON TABLE {}.{} TO {}").format(
                        sql.SQL(", ").join(sql.SQL(privilege) for privilege in privileges),
                        sql.Identifier("public"),
                        sql.Identifier(table),
                        sql.Identifier(role),
                    )
                )
        committed = True

        candidate_url = urlunsplit(
            ("postgresql", urlsplit(app_url).netloc, parsed.path, parsed.query, "")
        )
        with psycopg.connect(candidate_url) as candidate:
            candidate_user, privileged = candidate.execute(
                "SELECT current_user, rolsuper OR rolcreatedb OR rolcreaterole "
                "OR rolreplication OR rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            revision = candidate.execute("SELECT version_num FROM alembic_version").fetchone()
            if candidate_user != role or privileged or revision is None:
                raise RotationError(
                    "new runtime login did not pass its least-privilege access check"
                )
            for table, privileges in RUNTIME_TABLE_PRIVILEGES.items():
                for privilege in privileges:
                    can_access = candidate.execute(
                        "SELECT has_table_privilege(current_user, %s, %s)",
                        (f"public.{table}", privilege),
                    ).fetchone()[0]
                    if not can_access:
                        raise RotationError(
                            "new runtime login is missing a reviewed table privilege"
                        )

        print("PASS - new runtime role staged and verified with read access to Alembic revision")
        print("PASS - old database role and active application configuration were left unchanged")
        print(f"PASS - protected Compose environment file created at {output_path} with mode 0600")
        print(
            "NEXT STEP - application switch and old-role revocation require a separately approved cutover"
        )
        return 0
    except RotationError as exc:
        if output_path is not None and output_inode is not None and not committed:
            remove_own_file(output_path, output_inode)
        if committed:
            print(
                "FAIL - role staging committed but access verification failed; "
                "preserve the credential file and inspect the staged role",
                file=sys.stderr,
            )
            if output_path is not None:
                print(
                    f"FAIL - protected credential file retained at {output_path}",
                    file=sys.stderr,
                )
            return 1
        print(f"BLOCKED - credential rotation: {exc}", file=sys.stderr)
        return 2
    except (ImportError, OSError, ValueError):
        if output_path is not None and output_inode is not None and not committed:
            remove_own_file(output_path, output_inode)
        detail = "staged role may exist" if committed else "no existing role was changed"
        print(
            f"FAIL - credential staging failed; database details were suppressed; {detail}",
            file=sys.stderr,
        )
        if committed and output_path is not None:
            print(
                f"FAIL - retain and inspect the protected credential file at {output_path}",
                file=sys.stderr,
            )
        return 1
    except driver_error_types:
        if output_path is not None and output_inode is not None and not committed:
            remove_own_file(output_path, output_inode)
        detail = "staged role may exist" if committed else "no existing role was changed"
        print(
            f"FAIL - credential staging failed; database details were suppressed; {detail}",
            file=sys.stderr,
        )
        if committed and output_path is not None:
            print(
                f"FAIL - retain and inspect the protected credential file at {output_path}",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
