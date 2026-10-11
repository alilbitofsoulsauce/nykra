import tempfile
import unittest

from nykra.evaluation import EvaluatedExploration, EvaluatorResult
from nykra.replay import replay
from nykra.store import HistoryStore, NykraError


class EvaluatedExplorationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(self.temp.name)

    def test_trusted_evaluator_scores_linked_candidates(self):
        harness = EvaluatedExploration(
            self.store, evaluator_id="metric-v1",
            evaluate=lambda candidate: EvaluatorResult(score=sum(candidate)))
        run = harness.begin(task="toy quality metric", agent="supervised-agent")
        a = harness.attempt(run_id=run["id"], attempt_id="a", candidate=[1, 1])
        b = harness.attempt(run_id=run["id"], attempt_id="b", parent_id="a",
                            candidate=[3, 4])
        self.assertEqual(a["score"], 2)
        self.assertEqual(b["score"], 7)
        self.assertEqual(replay(self.store, run_id=run["id"])["best_score"], 7)
        self.assertEqual(self.store.stats()["activity_count"], 0)
        self.assertEqual(b["metadata"]["evaluator_id"], "metric-v1")

    def test_evaluation_failure_does_not_leak_private_exception(self):
        def fail(candidate):
            raise RuntimeError("SECRET_OUTPUT candidate code")

        harness = EvaluatedExploration(self.store, evaluator_id="metric-v1", evaluate=fail)
        run = harness.begin(task="evaluation failure", agent="supervised-agent")
        event = harness.attempt(run_id=run["id"], candidate={"prompt": "PRIVATE"})
        self.assertEqual(event["status"], "failed")
        self.assertIsNone(event["score"])
        self.assertNotIn("SECRET", str(event))
        self.assertNotIn("PRIVATE", str(event))

    def test_evaluator_id_is_fixed_per_run(self):
        harness = EvaluatedExploration(
            self.store, evaluator_id="metric-v1",
            evaluate=lambda _: EvaluatorResult(1))
        other = self.store.create_run(task="other", agent="agent", evaluator_id="metric-v2")
        with self.assertRaises(NykraError):
            harness.attempt(run_id=other["id"], candidate=1)
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_invalid_metric_is_rejected_not_stored(self):
        harness = EvaluatedExploration(
            self.store, evaluator_id="metric-v1",
            evaluate=lambda _: EvaluatorResult(float("nan")))
        run = harness.begin(task="bad eval", agent="agent")
        with self.assertRaises(NykraError):
            harness.attempt(run_id=run["id"], candidate=1)
        self.assertEqual(self.store.stats()["attempt_count"], 0)


if __name__ == "__main__":
    unittest.main()
