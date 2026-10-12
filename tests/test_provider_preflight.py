"""No-credential tests for an approved external inference-provider readiness gate."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nykra.provider_preflight import probe_command, probe_repeated


class ProviderPreflightTests(unittest.TestCase):
    def cmd(self, body):
        return [sys.executable, "-B", "-c", body]

    def test_explicit_approval_required(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            probe_command(self.cmd("print('READY')"))
        with self.assertRaisesRegex(ValueError, "approval"):
            probe_repeated(self.cmd("print('READY')"))

    def test_real_ready_response(self):
        report = probe_command(self.cmd("print('READY')"), approve=True)
        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["ready"])
        self.assertEqual(report["exit_code"], 0)
        self.assertTrue(report["output_redacted"])
        self.assertGreater(report["stdout_bytes"], 0)
        self.assertNotIn("READY", str(report["stdout_sha256"]))

    def test_empty_output_does_not_count(self):
        result = probe_command(self.cmd("pass"), approve=True)
        self.assertEqual(result["status"], "empty_response")
        self.assertFalse(result["ready"])

    def test_substring_and_leaked_stderr_rejected(self):
        result = probe_command(
            self.cmd("import sys; print('READY plus extra'); print('SECRET_KEY_FAKE', file=sys.stderr)"),
            approve=True,
        )
        self.assertEqual(result["status"], "unexpected_response")
        self.assertTrue(result["output_redacted"])
        self.assertNotIn("SECRET_KEY_FAKE", str(result))
        self.assertNotIn("READY plus extra", str(result))

    def test_nonzero_exit_fails_even_with_ready_marker(self):
        result = probe_command(self.cmd("print('READY'); raise SystemExit(4)"), approve=True)
        self.assertEqual(result["status"], "process_error")
        self.assertEqual(result["exit_code"], 4)
        self.assertFalse(result["ready"])

    def test_timeout_is_not_a_coding_attempt(self):
        result = probe_repeated(
            self.cmd("import time; time.sleep(8)"), runs=1,
            timeout=1, approve=True,
        )
        self.assertFalse(result["all_ready"])
        self.assertEqual(result["attempts"][0]["status"], "timeout")
        self.assertIsNone(result["attempts"][0]["exit_code"])
        self.assertEqual(result["scored_coding_attempts"], 0)

    def test_invalid_arguments(self):
        for kwargs in ({"timeout": 0}, {"timeout": 121},
                       {"expect": ""}, {"expect": "A\nB"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    probe_command(self.cmd("print('READY')"), approve=True, **kwargs)
        for count in (0, 4, 1.5):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    probe_repeated(self.cmd("print('READY')"),
                                   approve=True, runs=count)

    def test_cli_cross_process_and_repeated_invocations(self):
        with tempfile.TemporaryDirectory(prefix="nykra-provider-preflight-") as directory:
            command = [
                sys.executable, "-m", "nykra", "provider-probe",
                "--runs", "2", "--timeout", "10", "--cwd", directory,
                "--approve", "--", sys.executable, "-B", "-c", "print('READY')",
            ]
            checked = subprocess.run(command, capture_output=True, text=True,
                                     encoding="utf-8", timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            report = json.loads(checked.stdout)
            self.assertTrue(report["all_ready"])
            self.assertEqual(report["ready_count"], 2)
            self.assertEqual(report["scored_coding_attempts"], 0)
            self.assertFalse(report["model_inference_authenticated"])
            self.assertFalse(report["free_model_verified"])

    def test_nonexistent_executable_is_an_infrastructure_failure(self):
        result = probe_command(["_missing_nykra_provider_executable_xyz_"],
                               approve=True)
        self.assertEqual(result["status"], "spawn_error")
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
