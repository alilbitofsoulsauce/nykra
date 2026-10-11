"""External repository execution must fail closed without a verified sandbox."""
import unittest
from unittest.mock import patch
from nykra.external_isolation import isolation_preflight, require_verified_external_isolation
from nykra.store import NykraError


class IsolationTests(unittest.TestCase):
    def test_missing_runtime_blocks_external_execution(self):
        with patch("nykra.external_isolation.shutil.which", return_value=None):
            status = isolation_preflight()
        self.assertFalse(status["execution_authorized"])
        self.assertFalse(status["external_benchmark_ready"])
        self.assertFalse(status["ready_for_container_smoke_test"])
        self.assertFalse(status["image_digest_locked"])
        self.assertFalse(status["wsl"]["counts_as_verified_isolation"])
        for backend in ("docker", "podman"):
            self.assertFalse(status["container_runtimes"][backend]["detected"])
        with self.assertRaises(NykraError):
            require_verified_external_isolation(status, smoke_attestation=True)

    def test_detected_wsl_without_container_is_not_sandbox(self):
        def which(name):
            return "/usr/bin/wsl" if name == "wsl" else None
        with patch("nykra.external_isolation.shutil.which", side_effect=which), \
             patch("nykra.external_isolation.subprocess.run") as run:
            run.return_value.returncode = 0
            result = isolation_preflight()
        self.assertTrue(result["wsl"]["responding"])
        self.assertFalse(result["ready_for_container_smoke_test"])

    def test_container_runtime_does_not_authorize_execution_without_image(self):
        def which(name):
            return "/path/docker" if name == "docker" else None
        with patch("nykra.external_isolation.shutil.which", side_effect=which), \
             patch("nykra.external_isolation.subprocess.run") as run:
            run.return_value.returncode = 0
            result = isolation_preflight(image="docker.io/library/python:3.13")
        self.assertTrue(result["container_runtimes"]["docker"]["responding"])
        self.assertFalse(result["image_digest_locked"])
        self.assertFalse(result["ready_for_container_smoke_test"])
        self.assertFalse(result["execution_authorized"])

    def test_sha_digest_image_only_and_no_implicit_execution(self):
        digest = "docker.io/library/python@sha256:" + "c" * 64
        with patch("nykra.external_isolation.shutil.which", side_effect=lambda name: (
                "/docker" if name == "docker" else None)), \
             patch("nykra.external_isolation.subprocess.run") as run:
            run.return_value.returncode = 0
            result = isolation_preflight(image=digest)
        self.assertTrue(result["image_digest_locked"])
        self.assertTrue(result["image_available_locally"])
        self.assertTrue(result["ready_for_container_smoke_test"])
        self.assertFalse(result["execution_authorized"])
        with self.assertRaises(NykraError):
            require_verified_external_isolation(result, smoke_attestation=True)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all("--network" not in str(args) for args in run.call_args_list))

    def test_dead_service_never_marked_ready(self):
        with patch("nykra.external_isolation.shutil.which", side_effect=lambda name: (
                "/docker" if name == "docker" else None)), \
             patch("nykra.external_isolation.subprocess.run") as run:
            run.return_value.returncode = 125
            status = isolation_preflight(image="python@sha256:" + "d" * 64)
        self.assertFalse(status["ready_for_container_smoke_test"])
        self.assertEqual(status["container_runtimes"]["docker"]["reason"], "service_not_ready")


if __name__ == "__main__":
    unittest.main()
