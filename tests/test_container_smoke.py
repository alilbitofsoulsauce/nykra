"""Fixed Docker smoke enforces restrictions but cannot authorize hostile code."""
import subprocess
import unittest
from unittest.mock import patch

from nykra.container_smoke import run_container_smoke
from nykra.store import NykraError

IMAGE = "docker.io/library/busybox@sha256:" + "a" * 64
READY = {
    "ready_for_container_smoke_test": True,
    "container_runtimes": {"docker": {"responding": True}},
}


class ContainerSmokeTests(unittest.TestCase):
    def test_approval_required_before_preflight(self):
        with patch("nykra.container_smoke.isolation_preflight") as preflight:
            with self.assertRaises(NykraError):
                run_container_smoke(image=IMAGE)
            preflight.assert_not_called()

    def test_missing_image_blocks_execution(self):
        with patch("nykra.container_smoke.isolation_preflight",
                   return_value={**READY, "ready_for_container_smoke_test": False}), \
             patch("nykra.container_smoke.subprocess.run") as proc:
            with self.assertRaises(NykraError):
                run_container_smoke(image=IMAGE, approval=True)
            proc.assert_not_called()

    def test_restricted_run_and_evidence_do_not_grant_external_access(self):
        with patch("nykra.container_smoke.isolation_preflight", return_value=READY), \
             patch("nykra.container_smoke.shutil.which", return_value="docker"), \
             patch("nykra.container_smoke.secrets.token_hex", return_value="fixednonce"), \
             patch("nykra.container_smoke.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "fixednonce\n", "")) as proc:
            report = run_container_smoke(image=IMAGE, approval=True)
        self.assertTrue(report["smoke_passed"])
        self.assertFalse(report["execution_authorized"])
        self.assertFalse(report["external_benchmark_ready"])
        self.assertFalse(report["untrusted_repository_code_executed"])
        argv = proc.call_args.args[0]
        for expected in ("--network", "none", "--read-only", "--cap-drop", "ALL",
                         "--security-opt", "no-new-privileges",
                         "--pids-limit", "64", "--user", "65534:65534",
                         "--pull", "never", "--memory", "128m",
                         "--cpus", "1", "--tmpfs"):
            self.assertIn(expected, argv)
        self.assertEqual(argv[-3], IMAGE)
        self.assertNotIn("-v", argv)
        self.assertNotIn("--privileged", argv)
        self.assertEqual(proc.call_args.kwargs["timeout"], 25)

    def test_forged_output_and_nonzero_exit_are_rejected(self):
        for code, stdout in ((0, "wrong"), (7, "fixednonce\n")):
            with self.subTest(code=code):
                with patch("nykra.container_smoke.isolation_preflight", return_value=READY), \
                     patch("nykra.container_smoke.shutil.which", return_value="docker"), \
                     patch("nykra.container_smoke.secrets.token_hex", return_value="fixednonce"), \
                     patch("nykra.container_smoke.subprocess.run",
                           return_value=subprocess.CompletedProcess([], code, stdout, "secret")):
                    with self.assertRaisesRegex(NykraError, "exit/output"):
                        run_container_smoke(image=IMAGE, approval=True)

    def test_timeout_fails_closed(self):
        with patch("nykra.container_smoke.isolation_preflight", return_value=READY), \
             patch("nykra.container_smoke.shutil.which", return_value="docker"), \
             patch("nykra.container_smoke.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["docker"], 25)):
            with self.assertRaisesRegex(NykraError, "could not complete"):
                run_container_smoke(image=IMAGE, approval=True)


if __name__ == "__main__":
    unittest.main()
