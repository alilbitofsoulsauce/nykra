import tempfile
import unittest

from nykra.replay import replay
from nykra.store import HistoryStore, NykraError


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(self.temp.name)
        self.run = self.store.create_run(task="optimize", agent="test", evaluator_id="unit")

    def add(self, attempt_id, score, parent_id=None, status="ok"):
        return self.store.record_attempt(
            run_id=self.run["id"], attempt_id=attempt_id, score=score,
            parent_id=parent_id, status=status)

    def test_budget_and_order_are_prefix_observable(self):
        self.add("a", 1)
        self.add("b", 3)
        self.add("a1", 10, parent_id="a")
        self.add("b1", 5, parent_id="b")
        breadth = replay(self.store, run_id=self.run["id"], policy="breadth", budget=2)
        depth = replay(self.store, run_id=self.run["id"], policy="depth", budget=2)
        self.assertEqual(breadth["revealed_attempt_ids"], ["a", "b"])
        self.assertEqual(depth["revealed_attempt_ids"], ["a", "a1"])
        self.assertEqual(breadth["best_score"], 3)
        self.assertEqual(depth["best_score"], 10)
        self.assertEqual(breadth["replay_scope"], "recorded_outcomes_only")
        self.assertEqual(replay(self.store, run_id=self.run["id"], budget=0)["replayed_attempts"], 0)

    def test_unobserved_scores_cannot_change_first_decision(self):
        self.add("a", 1)
        self.add("b", 100)
        first = replay(self.store, run_id=self.run["id"], policy="adaptive", budget=1)
        other = self.store.create_run(task="same", agent="test", evaluator_id="unit")
        self.store.record_attempt(run_id=other["id"], attempt_id="c", score=1000)
        self.store.record_attempt(run_id=other["id"], attempt_id="d", score=-1000)
        second = replay(self.store, run_id=other["id"], policy="adaptive", budget=1)
        self.assertEqual(first["revealed_attempt_ids"], ["a"])
        self.assertEqual(second["revealed_attempt_ids"], ["c"])

    def test_minimize_failure_and_parallel_batches(self):
        run = self.store.create_run(task="minimize", agent="test", evaluator_id="unit", objective="minimize")
        self.store.record_attempt(run_id=run["id"], attempt_id="x", score=5)
        self.store.record_attempt(run_id=run["id"], attempt_id="y", score=2)
        self.store.record_attempt(run_id=run["id"], attempt_id="z", status="failed")
        result = replay(self.store, run_id=run["id"], policy="breadth", workers=2, budget=3)
        self.assertEqual(result["best_score"], 2)
        self.assertEqual(result["decision_rounds"], 2)
        self.assertEqual(result["replayed_attempts"], 3)
        self.assertEqual(result["attainment_curve"], [5, 2, 2])

    def test_invalid_replay_parameters(self):
        with self.assertRaises(NykraError):
            replay(self.store, run_id=self.run["id"], workers=0)
        with self.assertRaises(NykraError):
            replay(self.store, run_id=self.run["id"], budget=-1)
        with self.assertRaises(NykraError):
            replay(self.store, run_id=self.run["id"], policy="oracle")


if __name__ == "__main__":
    unittest.main()
