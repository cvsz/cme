import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.production import verify


class ProductionVerifyTests(unittest.TestCase):
    def test_recovery_policy_targets_reject_documentation_placeholders(self):
        self.assertTrue(verify.policy_target_configured("ISOLATED_TEST_ONLY"))
        for placeholder in (
            "REPLACE_WITH_OWNER_APPROVED_TARGET",
            "owner_approved",
            "TBD",
            "  ",
        ):
            with self.subTest(placeholder=placeholder):
                self.assertFalse(verify.policy_target_configured(placeholder))

    def test_container_inspection_uses_immutable_container_image_id(self):
        state = {"Status": "running", "Health": {"Status": "healthy"}}
        ports = {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18000"}]}
        output = "|".join(
            (
                "0",
                "sha256:" + "a" * 64,
                "b" * 40,
                json.dumps(state),
                json.dumps(ports),
            )
        )
        completed = subprocess.CompletedProcess(
            args=["docker", "inspect"], returncode=0, stdout=output, stderr=""
        )

        with patch.object(verify, "run", return_value=completed):
            inspected = verify.inspect_container("cme-api-1")

        self.assertEqual(inspected["restart_count"], 0)
        self.assertEqual(inspected["image_id"], "sha256:" + "a" * 64)
        self.assertEqual(inspected["release_sha"], "b" * 40)
        self.assertEqual(inspected["state"], state)
        self.assertEqual(inspected["ports"], ports)


if __name__ == "__main__":
    unittest.main()
