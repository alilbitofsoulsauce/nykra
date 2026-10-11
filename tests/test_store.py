import math
import tempfile
import unittest
from pathlib import Path

from nykra.store import HistoryStore, NykraError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(Path(self.temp.name))

    def test_run_and_parent_tree_persist(self):
        run = self.store.create_run(task="optimize", agent="test", evaluator_id="unit")
        a = self.store.record_attempt(run_id=run["id"], attempt_id="a", score=0.2)
        b = self.store.record_attempt(run_id=run["id"], attempt_id="b", parent_id="a",
                                      status="failed", metadata={"reason": "compile"})
        self.assertEqual(self.store.stats()["attempt_count"], 2)
        reopened = HistoryStore(self.temp.name)
        self.assertEqual(reopened.list_attempts(run["id"])[1]["parent_id"], a["id"])
        self.assertEqual(reopened.list_attempts(run["id"])[1]["metadata"]["reason"], "compile")
        self.assertIsNone(b["score"])

    def test_invalid_and_cross_run_attempts_rejected(self):
        one = self.store.create_run(task="one", agent="x", evaluator_id="eval")
        two = self.store.create_run(task="two", agent="x", evaluator_id="eval")
        self.store.record_attempt(run_id=one["id"], attempt_id="parent", score=1)
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=two["id"], parent_id="parent", score=2)
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=one["id"], score=float("nan"))
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=one["id"], status="ok", score=None)
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=one["id"], score=2, cost_units=-1)
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=one["id"], score=2, metadata={"nan": math.nan})
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=one["id"], attempt_id="parent", score=2)
        self.assertEqual(self.store.stats()["attempt_count"], 1)

    def test_bad_objective_and_unknown_parent(self):
        with self.assertRaises(NykraError):
            self.store.create_run(task="x", agent="a", evaluator_id="e", objective="anything")
        run = self.store.create_run(task="x", agent="a", evaluator_id="e")
        with self.assertRaises(NykraError):
            self.store.record_attempt(run_id=run["id"], parent_id="missing", score=1)

    def test_private_token_is_stable(self):
        a = self.store.token()
        self.assertTrue(self.store.authorize(a))
        self.assertFalse(self.store.authorize("incorrect"))
        self.assertEqual(a, HistoryStore(self.temp.name).token())


if __name__ == "__main__":
    unittest.main()
