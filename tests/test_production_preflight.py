import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.production import preflight


class ProductionPreflightTests(unittest.TestCase):
    def test_release_source_identity_requires_exact_clean_git_head(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo = Path(temporary_directory)

            def git(*arguments: str) -> str:
                result = subprocess.run(
                    ["git", "-C", str(repo), *arguments],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "-q")
            git("config", "user.email", "cme-test@example.invalid")
            git("config", "user.name", "CMe test")
            # Insulate the temporary repository from the host's global Git
            # signing policy so commit identity depends only on this test's
            # inputs and not on an operator's GPG/passphrase configuration.
            git("config", "commit.gpgsign", "false")
            (repo / "source.txt").write_text("committed source\n", encoding="utf-8")
            git("add", "source.txt")
            git("commit", "-qm", "test source")
            commit = git("rev-parse", "HEAD")

            with patch.object(preflight, "REPOSITORY_ROOT", repo):
                paths = ("source.txt",)
                self.assertTrue(preflight.build_context_matches_checkout("."))
                self.assertFalse(preflight.build_context_matches_checkout("/tmp"))
                self.assertTrue(
                    preflight.release_source_matches_checkout(commit, source_paths=paths)
                )
                self.assertFalse(
                    preflight.release_source_matches_checkout("0" * 40, source_paths=paths)
                )
                self.assertFalse(
                    preflight.release_source_matches_checkout("b" * 40, source_paths=paths)
                )

                (repo / "docs").mkdir()
                (repo / "docs/local.md").write_text("unrelated local note\n", encoding="utf-8")
                self.assertTrue(
                    preflight.release_source_matches_checkout(commit, source_paths=paths)
                )

                (repo / "source.txt").write_text("modified source\n", encoding="utf-8")
                self.assertFalse(
                    preflight.release_source_matches_checkout(commit, source_paths=paths)
                )

                git("checkout", "--", "source.txt")
                (repo / "untracked.py").write_text("uncommitted source\n", encoding="utf-8")
                self.assertFalse(
                    preflight.release_source_matches_checkout(
                        commit, source_paths=("untracked.py",)
                    )
                )

    def test_recovery_policy_targets_reject_documentation_placeholders(self):
        self.assertTrue(preflight.policy_target_configured("ISOLATED_TEST_ONLY"))
        for placeholder in (
            "REPLACE_WITH_OWNER_APPROVED_TARGET",
            "owner_approved",
            "TBD",
            "  ",
        ):
            with self.subTest(placeholder=placeholder):
                self.assertFalse(preflight.policy_target_configured(placeholder))

    def test_database_bootstrap_secret_must_be_strong_and_not_a_placeholder(self):
        self.assertTrue(preflight.strong_secret("A9!" + "b" * 30))
        for value in (
            None,
            "password",
            "short!A9",
            "REPLACE_ME" + "A9!" + "b" * 30,
            "a" * 32,
        ):
            with self.subTest(value_type=type(value).__name__):
                self.assertFalse(preflight.strong_secret(value))

    def test_compose_configuration_includes_ops_profile_for_migration_identity(self):
        with patch.dict(os.environ, {"CME_COMPOSE_ENV_FILES": ""}, clear=False):
            command = preflight.compose_config_command()

        self.assertEqual(
            command,
            ["docker", "compose", "--profile", "ops", "config", "--format", "json"],
        )

    def test_migration_probe_uses_the_migration_service_and_ops_profile(self):
        with patch.dict(os.environ, {"CME_COMPOSE_ENV_FILES": ""}, clear=False):
            command = preflight.migration_probe_command()

        self.assertEqual(command[2:7], ["--profile", "ops", "run", "--rm", "--no-deps"])
        self.assertIn("migrate", command)
        self.assertIn("pg_has_role", command[-1])
        self.assertIn("rolsuper", command[-1])

    def test_database_identity_decodes_credentials_without_exposing_them(self):
        runtime = preflight.connection_identity(
            "postgresql+psycopg://runtime_user:runtime-secret@POSTGRES.:5432/cme"
        )
        migration = preflight.connection_identity(
            "postgresql+psycopg://migration_user:migration-secret@postgres/cme"
        )

        self.assertEqual(runtime, ("runtime_user", "postgres", 5432, "cme"))
        self.assertEqual(migration, ("migration_user", "postgres", 5432, "cme"))
        self.assertTrue(preflight.separate_roles_for_same_database(runtime, migration))

    def test_database_identity_rejects_same_role_or_different_database(self):
        runtime = preflight.connection_identity(
            "postgresql+psycopg://runtime_user:runtime-secret@postgres:5432/cme"
        )
        same_role = preflight.connection_identity(
            "postgresql+psycopg://runtime_user:another-secret@postgres:5432/cme"
        )
        different_database = preflight.connection_identity(
            "postgresql+psycopg://migration_user:migration-secret@postgres:5432/other"
        )

        self.assertFalse(preflight.separate_roles_for_same_database(runtime, same_role))
        self.assertFalse(preflight.separate_roles_for_same_database(runtime, different_database))
        self.assertIsNone(preflight.connection_identity("postgresql://user:bad%2@host/db"))


if __name__ == "__main__":
    unittest.main()
