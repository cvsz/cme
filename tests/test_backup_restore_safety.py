import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup-postgres.sh"
RESTORE_SCRIPT = ROOT / "scripts" / "restore-postgres.sh"
POSTGRES_CLIENT = ROOT / "scripts" / "production" / "postgres_client.py"
ROTATE_SCRIPT = ROOT / "scripts" / "production" / "rotate-db-credentials.py"
ROLLBACK_SCRIPT = ROOT / "scripts" / "production" / "rollback.py"
SYNTHETIC_DATABASE_URL = "postgresql://operator:synthetic-only@db.example.test:5432/cme"


class PostgresScriptSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def executable(self, name, content):
        path = self.bin_dir / name
        path.write_text(content)
        path.chmod(0o700)
        return path

    def environment(self, **overrides):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env['PATH']}"
        env.update(overrides)
        return env

    def run_script(self, script, env):
        return subprocess.run(
            ["sh", str(script)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_backup_refuses_to_overwrite_an_existing_backup(self):
        backup = self.root / "existing.dump"
        checksum = Path(f"{backup}.sha256")
        backup.write_bytes(b"operator backup data")
        checksum.write_text("existing checksum\n")
        invoked = self.root / "pg-dump-invoked"
        self.executable("pg_dump", f"#!/bin/sh\nprintf called > '{invoked}'\n")

        result = self.run_script(
            BACKUP_SCRIPT,
            self.environment(CME_DATABASE_URL=SYNTHETIC_DATABASE_URL, CME_BACKUP_FILE=str(backup)),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(backup.read_bytes(), b"operator backup data")
        self.assertEqual(checksum.read_text(), "existing checksum\n")
        self.assertFalse(invoked.exists())
        self.assertNotIn(SYNTHETIC_DATABASE_URL, result.stdout + result.stderr)

    def test_backup_publishes_new_archive_and_checksum_without_exposing_connection_url(
        self,
    ):
        backup = self.root / "new.dump"
        observed_arguments = self.root / "pg-dump-arguments"
        observed_pgpass = self.root / "pgpass-mode"
        self.executable(
            "pg_dump",
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "target = next(arg.split('=', 1)[1] for arg in sys.argv[1:] if arg.startswith('--file='))\n"
            f"pathlib.Path('{observed_arguments}').write_text(' '.join(sys.argv[1:]))\n"
            "import os\n"
            "pgpass = pathlib.Path(os.environ['PGPASSFILE'])\n"
            f"pathlib.Path('{observed_pgpass}').write_text(oct(pgpass.stat().st_mode & 0o777))\n"
            "assert 'synthetic-only' in pgpass.read_text()\n"
            "pathlib.Path(target).write_bytes(b'synthetic archive')\n",
        )
        self.executable("pg_restore", "#!/bin/sh\nexit 0\n")

        result = self.run_script(
            BACKUP_SCRIPT,
            self.environment(CME_DATABASE_URL=SYNTHETIC_DATABASE_URL, CME_BACKUP_FILE=str(backup)),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(backup.read_bytes(), b"synthetic archive")
        self.assertEqual(
            Path(f"{backup}.sha256").read_text().strip(),
            hashlib.sha256(b"synthetic archive").hexdigest(),
        )
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SYNTHETIC_DATABASE_URL, observed_arguments.read_text())
        self.assertNotIn("synthetic-only", observed_arguments.read_text())
        self.assertEqual(observed_pgpass.read_text(), "0o600")
        self.assertNotIn(SYNTHETIC_DATABASE_URL, result.stdout + result.stderr)

    def test_compose_backup_runs_client_inside_postgres_and_keeps_credentials_out_of_argv(
        self,
    ):
        backup = self.root / "compose.dump"
        observed_args = self.root / "docker-arguments.jsonl"
        observed_pgpass = self.root / "compose-pgpass"
        observed_pgpass_mode = self.root / "compose-pgpass-mode"
        fake_docker = (
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            f"with pathlib.Path({str(observed_args)!r}).open('a') as stream: "
            "stream.write(json.dumps(args) + '\\n')\n"
            "if 'cp' in args:\n"
            "    index = args.index('cp')\n"
            "    source, destination = args[index + 1:index + 3]\n"
            "    if source.startswith('postgres:'):\n"
            "        pathlib.Path(destination).write_bytes(b'synthetic compose archive')\n"
            "    else:\n"
            "        source_path = pathlib.Path(source)\n"
            f"        pathlib.Path({str(observed_pgpass)!r}).write_text(source_path.read_text())\n"
            f"        pathlib.Path({str(observed_pgpass_mode)!r}).write_text(oct(source_path.stat().st_mode & 0o777))\n"
            "if 'exec' in args and 'pg_dump' in args:\n"
            "    sys.stdout.buffer.write(b'synthetic compose archive')\n"
        )
        self.executable("docker", fake_docker)
        self.executable("pg_restore", "#!/bin/sh\nexit 0\n")

        result = self.run_script(
            BACKUP_SCRIPT,
            self.environment(
                CME_POSTGRES_CLIENT_MODE="compose",
                CME_DATABASE_URL=SYNTHETIC_DATABASE_URL,
                CME_BACKUP_FILE=str(backup),
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(backup.read_bytes(), b"synthetic compose archive")
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(observed_pgpass_mode.read_text(), "0o600")
        self.assertIn("synthetic-only", observed_pgpass.read_text())
        invocations = [json.loads(line) for line in observed_args.read_text().splitlines()]
        joined = " ".join(argument for invocation in invocations for argument in invocation)
        self.assertIn("pg_dump", joined)
        self.assertNotIn("synthetic-only", joined)
        self.assertNotIn(SYNTHETIC_DATABASE_URL, joined)
        pgpass_path = next(
            argument
            for invocation in invocations
            for argument in invocation
            if argument.startswith("/tmp/cme-pgpass-")
        )
        self.assertFalse(Path(pgpass_path).exists())
        self.assertEqual(
            Path(f"{backup}.sha256").read_text().strip(),
            hashlib.sha256(b"synthetic compose archive").hexdigest(),
        )
        self.assertNotIn(SYNTHETIC_DATABASE_URL, result.stdout + result.stderr)

    def test_compose_backup_fails_if_temporary_database_credentials_cannot_be_removed(
        self,
    ):
        backup = self.root / "compose-cleanup-failure.dump"
        self.executable(
            "docker",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "if 'rm' in args:\n"
            "    raise SystemExit(1)\n"
            "if 'exec' in args and 'pg_dump' in args:\n"
            "    sys.stdout.buffer.write(b'synthetic compose archive')\n",
        )
        self.executable("pg_restore", "#!/bin/sh\nexit 0\n")

        result = self.run_script(
            BACKUP_SCRIPT,
            self.environment(
                CME_POSTGRES_CLIENT_MODE="compose",
                CME_DATABASE_URL=SYNTHETIC_DATABASE_URL,
                CME_BACKUP_FILE=str(backup),
            ),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("temporary PostgreSQL credential cleanup failed", result.stderr)
        self.assertFalse(backup.exists())
        self.assertNotIn(SYNTHETIC_DATABASE_URL, result.stdout + result.stderr)

    def test_restore_requires_explicit_destructive_authorization(self):
        backup = self.root / "restore.dump"
        backup.write_bytes(b"synthetic archive")
        Path(f"{backup}.sha256").write_text(f"{hashlib.sha256(backup.read_bytes()).hexdigest()}\n")
        invoked = self.root / "restore-invoked"
        self.executable("psql", f"#!/bin/sh\nprintf called > '{invoked}'\nprintf cme_restore\n")
        self.executable("pg_restore", f"#!/bin/sh\nprintf called >> '{invoked}'\n")

        result = self.run_script(
            RESTORE_SCRIPT,
            self.environment(
                CME_APP_ENV="test",
                CME_DATABASE_URL=SYNTHETIC_DATABASE_URL,
                CME_BACKUP_FILE=str(backup),
                CME_RESTORE_CONFIRM_DATABASE="cme_restore",
            ),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CME_ALLOW_DESTRUCTIVE_RESTORE", result.stderr)
        self.assertFalse(invoked.exists())
        self.assertNotIn(SYNTHETIC_DATABASE_URL, result.stdout + result.stderr)

    def test_restore_refuses_a_database_name_mismatch_before_pg_restore(self):
        backup = self.root / "restore.dump"
        backup.write_bytes(b"synthetic archive")
        Path(f"{backup}.sha256").write_text(f"{hashlib.sha256(backup.read_bytes()).hexdigest()}\n")
        invoked = self.root / "pg-restore-invoked"
        self.executable("psql", "#!/bin/sh\nprintf other_database\n")
        self.executable(
            "pg_restore",
            "#!/bin/sh\n"
            f'for arg in "$@"; do [ "$arg" != --clean ] || printf called > \'{invoked}\'; done\n',
        )

        result = self.run_script(
            RESTORE_SCRIPT,
            self.environment(
                CME_APP_ENV="test",
                CME_DATABASE_URL=SYNTHETIC_DATABASE_URL,
                CME_BACKUP_FILE=str(backup),
                CME_RESTORE_CONFIRM_DATABASE="cme_restore",
                CME_ALLOW_DESTRUCTIVE_RESTORE="YES",
            ),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match", result.stderr)
        self.assertFalse(invoked.exists())

    def test_live_restore_requires_a_separate_operator_approval(self):
        invoked = self.root / "restore-invoked"
        self.executable("psql", f"#!/bin/sh\nprintf called > '{invoked}'\n")

        result = self.run_script(
            RESTORE_SCRIPT,
            self.environment(
                CME_APP_ENV="production",
                CME_DATABASE_URL=SYNTHETIC_DATABASE_URL,
                CME_BACKUP_FILE=str(self.root / "missing.dump"),
                CME_RESTORE_CONFIRM_DATABASE="cme",
                CME_ALLOW_DESTRUCTIVE_RESTORE="YES",
            ),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit live recovery approval", result.stderr)
        self.assertFalse(invoked.exists())

    def test_live_credential_staging_requires_explicit_approval(self):
        env = self.environment(
            CME_APP_ENV="production",
            CME_ROTATION_ADMIN_URL=SYNTHETIC_DATABASE_URL,
            CME_ROTATION_CONFIRM_DATABASE="cme",
            CME_ROTATION_ROLE="cme_runtime_next",
            CME_ROTATION_MIGRATION_ROLE="cme_migrator",
            CME_ROTATION_OUTPUT_FILE=str(self.root / "runtime.env"),
        )
        env.pop("CME_ROTATION_APPROVAL", None)

        result = subprocess.run(
            ["python3", str(ROTATE_SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit CME_ROTATION_APPROVAL", result.stderr)
        self.assertNotIn("synthetic-only", result.stdout + result.stderr)
        self.assertFalse((self.root / "runtime.env").exists())

    def test_credential_staging_in_test_mode_requires_loopback_database(self):
        result = subprocess.run(
            ["python3", str(ROTATE_SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(
                CME_APP_ENV="test",
                CME_ROTATION_ADMIN_URL=SYNTHETIC_DATABASE_URL,
                CME_ROTATION_CONFIRM_DATABASE="cme",
                CME_ROTATION_ROLE="cme_runtime_next",
                CME_ROTATION_MIGRATION_ROLE="cme_migrator",
                CME_ROTATION_OUTPUT_FILE=str(self.root / "runtime.env"),
            ),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("restricted to a loopback", result.stderr)
        self.assertNotIn("synthetic-only", result.stdout + result.stderr)
        self.assertFalse((self.root / "runtime.env").exists())

    def test_live_application_rollback_requires_explicit_approval(self):
        result = subprocess.run(
            ["python3", str(ROLLBACK_SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(CME_APP_ENV="production"),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit CME_ROLLBACK_APPROVAL", result.stdout)
        self.assertNotIn("synthetic-only", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
