"""v0.31 real free-model study reproducibility without another provider call."""
import json
import unittest

from scripts.summarize_live_efficiency_v31 import SUMMARY, RUNS, summarize


class V31EfficiencyStudyTests(unittest.TestCase):
    def test_raw_provider_model_and_public_receipts_reconcile(self):
        saved = json.loads(SUMMARY.read_text(encoding="utf-8"))
        recomputed = summarize()
        self.assertEqual(saved, recomputed)
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["task_count"], 3)
        self.assertEqual(len(saved["historical_projects"]), 2)
        self.assertTrue(saved["independent_model_calls_per_arm"])
        self.assertTrue(saved["identical_first_prompt_per_issue"])
        self.assertFalse(saved["causal_coding_accuracy_uplift_proven"])
        original = saved["arms"]["baseline_depth"]
        optimized = saved["arms"]["nykra_optimized_depth"]
        self.assertEqual(original["hidden_verified_tasks_solved"], 1)
        self.assertEqual(optimized["hidden_verified_tasks_solved"], 1)
        self.assertEqual(original["actual_provider_calls"], 8)
        self.assertEqual(optimized["actual_provider_calls"], 8)
        self.assertEqual(original["provider_reported_tokens"], 3498)
        self.assertEqual(optimized["provider_reported_tokens"], 3499)
        self.assertEqual(original["public_docker_evaluations"], 8)
        self.assertEqual(optimized["public_docker_evaluations"], 6)
        self.assertEqual(optimized["public_docker_evaluations_reused"], 2)
        self.assertEqual(original["public_docker_evaluations_reused"], 0)
        self.assertEqual(optimized["early_halts"], 0)
        self.assertEqual(saved["comparisons"]["public_docker_avoidance_fraction"], 0.25)

    def test_repeats_are_real_and_hidden_suite_only_runs_after_public_pass(self):
        saved = json.loads(SUMMARY.read_text(encoding="utf-8"))
        for task in saved["tasks"]:
            with self.subTest(task=task["task"]):
                raw = json.loads((RUNS / (task["task"]+".json")).read_text())
                self.assertTrue(raw["hidden_evaluated_after_arms"])
                self.assertEqual(raw["status"], "completed")
                self.assertEqual(len(raw["arms"]), 2)
                for arm in raw["arms"]:
                    self.assertEqual(arm["status"], "completed")
                    self.assertEqual(arm["model_calls_avoided"], 0)
                    self.assertEqual(
                        arm["model_provider_calls"], len(arm["attempts"]))
                    self.assertTrue(
                        all(t["model_provider_reported_cost"] == 0 for t in arm["attempts"]))
                    self.assertTrue(
                        all(not t["model_cache_hit"] for t in arm["attempts"]))
                    has_public = any(a["public"]["passed"] for a in arm["attempts"])
                    self.assertEqual(has_public, "hidden_checks" in arm)

    def test_cache_reuses_real_identical_failed_candidate_and_not_just_status(self):
        for task_id, prior in (("tqdm-1", 2), ("youtube-dl-43", 1)):
            with self.subTest(task=task_id):
                trial = json.loads((RUNS / (task_id+".json")).read_text())
                optimized = next(x for x in trial["arms"]
                                 if x["arm"] == "nykra_optimized_depth")
                last = optimized["attempts"][2]
                original = optimized["attempts"][prior-1]
                self.assertEqual(last["source_sha256"], original["source_sha256"])
                self.assertTrue(last["public_grade_reused"])
                self.assertEqual(last["public_grade_source_attempt"], prior)
                self.assertFalse(last["public"]["passed"])
                self.assertEqual(last["public"], original["public"])


if __name__ == "__main__":
    unittest.main()
