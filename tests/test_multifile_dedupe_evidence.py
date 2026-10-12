"""Prove the frozen v0.29 Docker receipt without invoking Docker in CI."""
import json
import unittest
from pathlib import Path

from scripts.measure_multifile_dedupe import measure

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/v29_multifile_dedupe_docker.json"


class DuplicateReplayEvidenceTests(unittest.TestCase):
    def test_approval_required_before_local_git_and_docker_work(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            measure(image="sha256:" + "a" * 64)
        with self.assertRaisesRegex(ValueError, "sha256"):
            measure(image="python:3.13", approve=True)

    def test_raw_receipt_reconciles_exact_attempt_and_runner_counts(self):
        trial = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(trial["schema"],
                         "nykra-real-docker-duplicate-work-replay-v1")
        self.assertEqual(trial["evaluator_calls_without_cache"], 7)
        self.assertEqual(trial["evaluator_calls_with_cache"], 4)
        self.assertEqual(trial["avoided_docker_evaluations"], 3)
        self.assertAlmostEqual(trial["avoided_fraction"], 3/7)
        self.assertTrue(trial["fixture_clean_after"])
        self.assertTrue(trial["same_model_attempt_budgets"])
        self.assertFalse(trial["task_success_without_cache"])
        self.assertFalse(trial["task_success_with_cache"])
        self.assertEqual(len(trial["runs"]), 4)
        for run in trial["runs"]:
            with self.subTest(policy=run["policy"], dedupe=run["dedupe_enabled"]):
                attempts = run["attempts"]
                public = run["public_work"]
                self.assertEqual(len(attempts), len(run["submitted_patches"]))
                self.assertEqual(len(attempts), public["model_attempts_recorded"])
                self.assertEqual(public["public_evaluator_reuses"],
                                 sum(x["reused"] for x in attempts))
                self.assertEqual(public["public_evaluator_calls"],
                                 sum(not x["reused"] for x in attempts))
                self.assertEqual(
                    public["public_evaluator_calls"] + public["public_evaluator_reuses"],
                    len(attempts),
                )
                self.assertTrue(run["finalized_without_passing_patch"])
                self.assertTrue(all(x["status"] == "test_failed" for x in attempts))
                self.assertTrue(all(x["tests_run_original"] == 2 for x in attempts))
                self.assertTrue(all(x["tests_executed_now"] == (0 if x["reused"] else 2)
                                    for x in attempts))
        depth_off, depth_on, adaptive_on, adaptive_off = trial["runs"]
        self.assertEqual((depth_off["policy"], depth_on["policy"]),
                         ("depth", "depth"))
        self.assertEqual((adaptive_on["policy"], adaptive_off["policy"]),
                         ("adaptive", "adaptive"))
        self.assertEqual(
            [x["controller_action"] for x in adaptive_on["attempts"]],
            [x["controller_action"] for x in adaptive_off["attempts"]],
        )
        self.assertEqual(adaptive_on["attempts"][-1]["controller_action"], "new_root")
        self.assertEqual(depth_on["public_work"]["public_evaluator_calls"], 1)
        self.assertEqual(adaptive_on["public_work"]["public_evaluator_calls"], 3)


if __name__ == "__main__":
    unittest.main()
