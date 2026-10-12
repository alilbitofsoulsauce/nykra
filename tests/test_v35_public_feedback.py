"""Public-only diagnostic grader: no host execution or hidden-suite leakage."""
import subprocess
import unittest
from unittest.mock import patch

from nykra import v35_public_feedback as feedback


TASK = {
    "id": "youtube-dl-5",
    "function": "unified_timestamp",
    "buggy_commit": "historical-bug",
    "public_test": "test.test_utils.TestUtil.test_unified_timestamps",
}
BUGGY = "def unified_timestamp(value):\n    return value\n"
FIX = "def unified_timestamp(value):\n    return None\n"
# This fixture has the same function signature, so the replacement validator
# accepts it without requiring any untrusted code to run on the local host.


class V35PublicFeedbackTests(unittest.TestCase):
    def fixture(self):
        def apply_patch(*args, **kwargs):
            patcher = patch(*args, **kwargs)
            self.addCleanup(patcher.stop)
            return patcher.start()

        apply_patch("nykra.v35_public_feedback.manifest",
                    return_value=({"tasks": [TASK], "docker_image_id": "sha256:base"}, "sha256"))
        apply_patch("nykra.v35_public_feedback.function_at", return_value=BUGGY)
        apply_patch("nykra.v35_public_feedback.prepare",
                    side_effect=lambda task, root, replacement: (
                        root / "Dockerfile.nykra"
                    ).write_text("FROM scratch\n", encoding="utf-8"))
        apply_patch("nykra.v35_public_feedback._runner",
                    return_value=["-m", "unittest", TASK["public_test"]])

    @staticmethod
    def runner_result(args, *, failed=True):
        if args[:3] == ["docker", "image", "inspect"]:
            if args[-1] == feedback.IMAGE_TAG:
                return subprocess.CompletedProcess(args, 0, b"sha256:base\n", b"")
            return subprocess.CompletedProcess(args, 0, b"sha256:candidate\n", b"")
        if args[:2] == ["docker", "build"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if args[:2] == ["docker", "run"]:
            if failed:
                return subprocess.CompletedProcess(
                    args, 1, b"",
                    b"FAIL: test_unified_timestamps (test.test_utils.TestUtil)\n"
                    b"File /repo/test_public.py:11\n"
                    b"AssertionError: 1 != 2\nFAILED (failures=1)\n")
            return subprocess.CompletedProcess(args, 0, b"ok\n", b"")
        if args[:3] == ["docker", "image", "rm"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        raise AssertionError(f"unexpected subprocess command: {args}")

    def test_public_failure_diagnostic_is_bounded_and_pinned_docker_only(self):
        self.fixture()
        calls = []
        def fake(args, **kwargs):
            calls.append(args)
            return self.runner_result(args)
        with patch.object(feedback.subprocess, "run", side_effect=fake):
            result = feedback.grade_public_detailed(TASK, FIX)
        self.assertEqual(result["status"], "test_failed")
        self.assertFalse(result["passed"])
        self.assertIn("AssertionError: 1 != 2", result["diagnostic"])
        self.assertNotIn("/repo/", result["diagnostic"])
        self.assertLessEqual(len(result["diagnostic"]), 900)
        commands = [x for x in calls if x[:2] == ["docker", "run"]]
        self.assertEqual(len(commands), 1)
        runner = commands[0]
        self.assertIn("--network", runner)
        self.assertEqual(runner[runner.index("--network")+1], "none")
        self.assertIn("--read-only", runner)
        self.assertIn("--cap-drop", runner)
        self.assertEqual(runner[runner.index("--cap-drop")+1], "ALL")
        self.assertIn("--security-opt", runner)
        self.assertIn("no-new-privileges", runner)
        self.assertIn(TASK["public_test"], runner)
        self.assertFalse(any("hidden" in item for item in runner))

    def test_clean_public_pass_never_returns_failure_diagnostics(self):
        self.fixture()
        with patch.object(
            feedback.subprocess, "run",
            side_effect=lambda args, **kwargs: self.runner_result(args, failed=False)
        ):
            result = feedback.grade_public_detailed(TASK, FIX)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["passed"])
        self.assertNotIn("diagnostic", result)

    def test_mismatched_pinned_image_stops_before_materialization(self):
        self.fixture()
        with patch.object(feedback.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, b"sha256:unrecognized\n", b"")) as docker, patch.object(
                feedback, "prepare") as prepare:
            result = feedback.grade_public_detailed(TASK, FIX)
        self.assertEqual(result["status"], "evaluator_image_mismatch")
        docker.assert_called_once()
        prepare.assert_not_called()

    def test_invalid_candidate_refused_before_any_docker_call(self):
        self.fixture()
        with patch.object(feedback.subprocess, "run") as docker:
            result = feedback.grade_public_detailed(
                TASK, "def unified_timestamp(value, side_effect=1):\n    return 1\n")
        self.assertEqual(result["status"], "model_invalid_contract")
        docker.assert_not_called()

    def test_unallowlisted_task_is_rejected_before_any_docker(self):
        self.fixture()
        with patch.object(feedback.subprocess, "run") as docker:
            with self.assertRaisesRegex(ValueError, "not allowlisted"):
                feedback.grade_public_detailed(
                    {**TASK, "id": "unknown-task"}, FIX)
        docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
