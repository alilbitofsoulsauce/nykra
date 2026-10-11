"""Held-out separation, insufficiency gates and non-causal advisory output."""
import tempfile
import unittest

from nykra.intelligence import _partition, assess_policies
from nykra.store import HistoryStore, NykraError


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(self.temp.name)
        self.evaluator = "shared-benchmark-v1"

    def add_tree(self, task, *, strong_child=True, evaluator=None, objective="maximize"):
        run = self.store.create_run(task=task, agent="test", evaluator_id=evaluator or self.evaluator,
                                    objective=objective)
        rid = run["id"]
        if objective == "maximize":
            scores = [1, 2, 10 if strong_child else 1.5, 3]
        else:
            scores = [10, 9, 1 if strong_child else 9.5, 8]
        a = self.store.record_attempt(run_id=rid, score=scores[0])
        b = self.store.record_attempt(run_id=rid, score=scores[1])
        self.store.record_attempt(run_id=rid, parent_id=a["id"], score=scores[2])
        self.store.record_attempt(run_id=rid, parent_id=b["id"], score=scores[3])
        return rid

    def test_no_actual_evaluations_means_no_recommendation(self):
        self.store.record_activity(source="relai", tool="relai_exec",
                                   outcome="succeeded", duration_ms=10)
        result = assess_policies(self.store, evaluator_id=self.evaluator)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["recommendation"])
        self.assertFalse(result["can_auto_apply"])
        self.assertEqual(result["eligible_tasks"], 0)

    def test_task_disjoint_synthetic_can_produce_advisory_not_activation(self):
        for index in range(80):
            self.add_tree("unique-task-" + str(index))
        result = assess_policies(self.store, evaluator_id=self.evaluator, budget=2)
        self.assertEqual(result["status"], "advisory_candidate")
        self.assertIn(result["recommendation"]["policy"], {"depth", "adaptive"})
        self.assertFalse(result["can_auto_apply"])
        self.assertTrue(result["recommendation"]["requires_explicit_host_approval"])
        self.assertGreaterEqual(result["training_tasks"], 8)
        self.assertGreaterEqual(result["heldout_tasks"], 8)
        self.assertFalse(set(result["training_run_ids"]) & set(result["heldout_run_ids"]))
        self.assertLessEqual(result["heldout_sign_test"]["p_value"], .05)

    def test_candidate_chosen_without_heldout_lookahead(self):
        # Training favors depth; heldout favors breadth. Heldout must veto.
        for index in range(90):
            task = "split-task-" + str(index)
            training = _partition(self.evaluator, task, .33) == "training"
            self.add_tree(task, strong_child=training)
        result = assess_policies(self.store, evaluator_id=self.evaluator, budget=2)
        self.assertEqual(result["status"], "hold_baseline")
        self.assertEqual(result["selected_using_training_only"], "depth")
        self.assertIsNone(result["recommendation"])
        self.assertLess(result["heldout_mean_normalized_delta"], 0)

    def test_deduplicate_repeated_tasks(self):
        for index in range(40):
            self.add_tree("task-" + str(index))
        self.add_tree("task-0")
        result = assess_policies(self.store, evaluator_id=self.evaluator, budget=2)
        self.assertEqual(result["excluded"]["duplicate_task_runs"], 2)
        self.assertEqual(result["eligible_tasks"], 39)

    def test_evaluator_mismatch_does_not_contaminate(self):
        for index in range(40):
            self.add_tree("other-task-" + str(index), evaluator="other-metric")
        result = assess_policies(self.store, evaluator_id=self.evaluator, budget=2)
        self.assertEqual(result["original_runs"], 0)
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_minimize_objective(self):
        for index in range(80):
            self.add_tree("latency-task-" + str(index), objective="minimize")
        result = assess_policies(self.store, evaluator_id=self.evaluator, objective="minimize", budget=2)
        self.assertEqual(result["status"], "advisory_candidate")
        self.assertEqual(result["objective"], "minimize")

    def test_invalid_parameters(self):
        with self.assertRaises(NykraError):
            assess_policies(self.store, evaluator_id="x", budget=0)
        with self.assertRaises(NykraError):
            assess_policies(self.store, evaluator_id="x", objective="both")
        with self.assertRaises(NykraError):
            assess_policies(self.store, evaluator_id="x", holdout_fraction=.9)
        with self.assertRaises(NykraError):
            assess_policies(self.store, evaluator_id="x", min_heldout_tasks=1)


if __name__ == "__main__":
    unittest.main()
