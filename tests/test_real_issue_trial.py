"""Maintain fail-closed constraints and fair pilot setup."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nykra.real_issue_trial import read_manifest, task_prompt, run_task, grader


class RealIssueTests(unittest.TestCase):
    def setUp(self):
        self.protocol, self.digest = read_manifest()
        self.task = self.protocol["tasks"][0]

    def test_frozen_same_model_and_counterbalance(self):
        self.assertEqual(len(self.digest), 64)
        self.assertEqual(len(self.protocol["tasks"]), 4)
        self.assertEqual(self.protocol["attempts_per_arm"], 4)
        self.assertEqual([t["arm_order"] for t in self.protocol["tasks"]],
                         [["baseline", "nykra"], ["nykra", "baseline"],
                          ["baseline", "nykra"], ["nykra", "baseline"]])

    def test_model_never_gets_reference_commit(self):
        prompt = task_prompt(self.task, "def _match_one(): pass")
        self.assertIn(self.task["issue"], prompt)
        self.assertNotIn(self.task["fixed_commit"], prompt)
        self.assertNotIn("NYKRA POLICY", prompt)

    def test_requires_approval_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "run.json"
            with self.assertRaises(ValueError):
                run_task(self.task["id"], p)
            p.write_text("original", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                run_task(self.task["id"], p, approve=True)
            self.assertEqual(p.read_text(), "original")

    def test_oversized_candidate_never_calls_docker(self):
        with patch("nykra.real_issue_trial.subprocess.run") as execute:
            result = grader(self.task, replacement="a" * 20000)
        self.assertEqual(result["status"], "invalid_patch")
        execute.assert_not_called()

    def test_strict_docker_run_has_no_host_mount_or_network(self):
        observed = []
        def fake(argv, **kwargs):
            observed.append(argv)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        with patch("nykra.real_issue_trial.prepare"), \
             patch("nykra.real_issue_trial.subprocess.run", side_effect=fake), \
             patch("nykra.real_issue_trial.checked_run",
                   return_value=b"sha256:" + b"f" * 64):
            result = grader(self.task)
        self.assertTrue(result["passed"])
        cmd = next(x for x in observed if x[:2] == ["docker", "run"])
        for token in ("--read-only", "--network", "none", "--cap-drop",
                      "ALL", "--security-opt", "no-new-privileges",
                      "--memory", "--cpus", "--pids-limit", "--user"):
            self.assertIn(token, cmd)
        self.assertEqual(cmd[cmd.index("--user")+1], "65534:65534")
        for forbidden in ("--privileged", "-v", "--mount", "--volume"):
            self.assertNotIn(forbidden, cmd)


if __name__ == "__main__":
    unittest.main()
