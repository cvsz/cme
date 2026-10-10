#!/usr/bin/env python3
"""Run PostgreSQL client tools without exposing database passwords in argv or logs."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
LIBPQ_ENV = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "application_name": "PGAPPNAME",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "gssencmode": "PGGSSENCMODE",
    "channel_binding": "PGCHANNELBINDING",
}
COMPOSE_SERVICE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


def connection_values() -> tuple[str, str, str, str, str, dict[str, str]]:
    raw_value = os.environ.get("CME_DATABASE_URL", "").strip()
    file_value = os.environ.get("CME_DATABASE_URL_FILE", "").strip()
    if bool(raw_value) == bool(file_value):
        raise ValueError
    if raw_value:
        raw = raw_value
    else:
        secret_path = Path(file_value)
        if not secret_path.is_absolute() or secret_path.is_symlink():
            raise ValueError
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(secret_path, flags)
        secret_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(secret_stat.st_mode)
            or secret_stat.st_uid != os.geteuid()
            or secret_stat.st_mode & 0o077
        ):
            os.close(descriptor)
            raise ValueError
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            raw = stream.read().strip()
        if not raw or "\n" in raw or "\r" in raw:
            raise ValueError
    try:
        parsed = urlsplit(raw)
        if (
            parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgres"}
            or INVALID_PERCENT_ESCAPE.search(raw)
            or not parsed.hostname
            or not parsed.path.strip("/")
            or parsed.fragment
        ):
            raise ValueError
        host = parsed.hostname
        port = parsed.port or 5432
        username = unquote(parsed.username or "", errors="strict")
        password = unquote(parsed.password or "", errors="strict")
        database = unquote(parsed.path.strip("/"), errors="strict")
        if not username or any(
            "\n" in field or "\r" in field for field in (host, username, password, database)
        ):
            raise ValueError
        options: dict[str, str] = {}
        for key, value in parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True):
            if key not in LIBPQ_ENV or "\n" in value or "\r" in value:
                raise ValueError
            options[LIBPQ_ENV[key]] = value
        return host, str(port), username, database, password, options
    except (ValueError, TypeError, UnicodeError):
        raise ValueError from None


def pgpass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


@contextmanager
def pgpass_file(host: str, port: str, database: str, username: str, password: str):
    descriptor, filename = tempfile.mkstemp(prefix="cme-pgpass-", dir="/tmp")
    path = Path(filename)
    try:
        os.fchmod(descriptor, 0o600)
        line = ":".join(
            pgpass_escape(value) for value in (host, port, database, username, password)
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{line}\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def client_environment(pgpass: Path, options: dict[str, str]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PGPASSWORD", None)
    environment["PGPASSFILE"] = str(pgpass)
    environment.update(options)
    return environment


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    for env_file in os.environ.get("CME_COMPOSE_ENV_FILES", "").split(os.pathsep):
        if env_file:
            command.extend(["--env-file", env_file])
    compose_file = os.environ.get("CME_COMPOSE_FILE", "").strip()
    if compose_file:
        command.extend(["--file", compose_file])
    project_name = os.environ.get("CME_COMPOSE_PROJECT_NAME", "").strip()
    if project_name:
        command.extend(["--project-name", project_name])
    return [*command, *arguments]


def compose_service() -> str:
    service = os.environ.get("CME_POSTGRES_COMPOSE_SERVICE", "postgres").strip()
    if not COMPOSE_SERVICE_PATTERN.fullmatch(service):
        raise ValueError
    return service


def run_compose(
    command: list[str],
    *,
    timeout: int = 180,
    stdin=None,
    stdout=None,
) -> subprocess.CompletedProcess:
    options = {"capture_output": True, "text": True}
    if stdin is not None:
        options["stdin"] = stdin
    if stdout is not None:
        options.pop("capture_output")
        options.pop("text")
        options["stdout"] = stdout
        options["stderr"] = subprocess.PIPE
    return subprocess.run(command, check=False, timeout=timeout, **options)


def execute_compose_client(
    tool: str,
    arguments: list[str],
    *,
    output: bool = False,
) -> int:
    host, port, username, database, password, options = connection_values()
    service = compose_service()
    token = uuid.uuid4().hex
    remote_pgpass = f"/tmp/cme-pgpass-{token}"
    host_output: Path | None = None
    host_archive: Path | None = None
    if tool == "pg_dump":
        host_output = Path(
            next(arg.split("=", 1)[1] for arg in arguments if arg.startswith("--file="))
        )
        if (
            not host_output.is_absolute()
            or host_output.is_symlink()
            or not host_output.is_file()
            or host_output.stat().st_size != 0
        ):
            raise ValueError
    elif tool == "pg_restore":
        if not arguments:
            raise ValueError
        host_archive = Path(arguments[-1])
        if (
            not host_archive.is_absolute()
            or host_archive.is_symlink()
            or not host_archive.is_file()
        ):
            raise ValueError

    with pgpass_file(host, port, database, username, password) as pgpass:
        remote_files: list[str] = []
        try:
            remote_files.append(remote_pgpass)
            transfer = run_compose(compose_command("cp", str(pgpass), f"{service}:{remote_pgpass}"))
            if transfer.returncode != 0:
                print(
                    "FAIL: PostgreSQL credential transfer to the Compose service failed; details were suppressed.",
                    file=sys.stderr,
                )
                return transfer.returncode or 1
            ownership = run_compose(
                compose_command(
                    "exec",
                    "-T",
                    "--user",
                    "0",
                    service,
                    "chown",
                    "postgres:postgres",
                    *remote_files,
                )
            )
            if ownership.returncode != 0:
                print(
                    "FAIL: PostgreSQL client credential permissions could not be set; details were suppressed.",
                    file=sys.stderr,
                )
                return ownership.returncode or 1
            permissions = run_compose(
                compose_command("exec", "-T", "--user", "0", service, "chmod", "600", remote_pgpass)
            )
            if permissions.returncode != 0:
                print(
                    "FAIL: PostgreSQL client credential permissions could not be restricted; details were suppressed.",
                    file=sys.stderr,
                )
                return permissions.returncode or 1

            if tool == "pg_dump":
                client_arguments = [
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    f"--host={host}",
                    f"--port={port}",
                    f"--username={username}",
                    f"--dbname={database}",
                ]
            elif tool == "pg_restore":
                client_arguments = [
                    *arguments[:-1],
                    f"--host={host}",
                    f"--port={port}",
                    f"--username={username}",
                    f"--dbname={database}",
                ]
            else:
                client_arguments = [
                    *arguments,
                    f"--host={host}",
                    f"--port={port}",
                    f"--username={username}",
                    f"--dbname={database}",
                ]
            exec_arguments = ["exec", "-T"]
            for variable, value in options.items():
                exec_arguments.extend(["--env", f"{variable}={value}"])
            exec_arguments.extend(
                [
                    "--user",
                    "postgres",
                    service,
                    "sh",
                    "-c",
                    'umask 077; export PGPASSFILE="$1"; shift; exec "$@"',
                    "sh",
                    remote_pgpass,
                    tool,
                    *client_arguments,
                ]
            )
            command = compose_command(*exec_arguments)
            if tool == "pg_dump" and host_output is not None:
                with host_output.open("wb") as archive_output:
                    client = run_compose(command, timeout=300, stdout=archive_output)
                os.chmod(host_output, 0o600)
            elif tool == "pg_restore" and host_archive is not None:
                with host_archive.open("rb") as archive_input:
                    client = run_compose(command, timeout=300, stdin=archive_input)
            else:
                client = run_compose(command, timeout=300)
            if client.returncode != 0:
                print(
                    f"FAIL: {tool} failed inside the PostgreSQL Compose service with exit status {client.returncode}; details were suppressed.",
                    file=sys.stderr,
                )
                return client.returncode

            if output and client.stdout:
                sys.stdout.write(client.stdout)
            return 0
        finally:
            if remote_files:
                try:
                    cleanup = run_compose(
                        compose_command(
                            "exec",
                            "-T",
                            "--user",
                            "0",
                            service,
                            "rm",
                            "-f",
                            "--",
                            *remote_files,
                        ),
                        timeout=30,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    print(
                        "FAIL: temporary PostgreSQL credential cleanup could not be confirmed; inspect the Compose service temporary directory.",
                        file=sys.stderr,
                    )
                    raise
                if cleanup.returncode != 0:
                    print(
                        "FAIL: temporary PostgreSQL credential cleanup failed; inspect the Compose service temporary directory.",
                        file=sys.stderr,
                    )
                    raise ValueError


def execute_client(
    tool: str,
    arguments: list[str],
    *,
    connect: bool,
    output: bool = False,
) -> int:
    try:
        mode = os.environ.get("CME_POSTGRES_CLIENT_MODE", "local").strip().casefold()
        if mode not in {"local", "compose"}:
            raise ValueError
        if mode == "compose" and connect:
            return execute_compose_client(tool, arguments, output=output)
        if not connect:
            result = subprocess.run(
                [tool, *arguments],
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
        else:
            host, port, username, database, password, options = connection_values()
            with pgpass_file(host, port, database, username, password) as pgpass:
                environment = client_environment(pgpass, options)
                result = subprocess.run(
                    [
                        tool,
                        f"--host={host}",
                        f"--port={port}",
                        f"--username={username}",
                        *arguments,
                        f"--dbname={database}",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                    timeout=180,
                )
        if result.returncode == 0 and output:
            sys.stdout.write(result.stdout)
        elif result.returncode != 0:
            print(
                f"FAIL: {tool} failed; connection and database details were suppressed.",
                file=sys.stderr,
            )
        return result.returncode
    except (OSError, subprocess.TimeoutExpired, ValueError):
        print(
            "FAIL: PostgreSQL client operation failed; details were suppressed.",
            file=sys.stderr,
        )
        return 1


def main(arguments: list[str]) -> int:
    if not arguments:
        print("FAIL: a PostgreSQL client operation is required.", file=sys.stderr)
        return 2
    operation, *args = arguments
    if operation == "dump" and len(args) == 1:
        return execute_client(
            "pg_dump",
            ["--format=custom", "--no-owner", "--no-acl", f"--file={args[0]}"],
            connect=True,
        )
    if operation == "list" and len(args) == 1:
        return execute_client("pg_restore", ["--list", args[0]], connect=False)
    if operation == "database-name" and not args:
        return execute_client(
            "psql",
            ["--no-psqlrc", "-Atqc", "SELECT current_database()"],
            connect=True,
            output=True,
        )
    if operation == "restore" and len(args) == 1:
        return execute_client(
            "pg_restore",
            ["--clean", "--if-exists", "--no-owner", "--no-acl", args[0]],
            connect=True,
        )
    print("FAIL: PostgreSQL client operation is invalid.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
