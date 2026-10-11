"""Supervised callback safety, branching, and provenance tests."""
import tempfile
import unittest

from nykra.controller import Observation, Proposal, SupervisedController
from nykra.evaluation import EvaluatorResult
from nykra.store import HistoryStore, NykraError


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = HistoryStore(self.tmp.name)
        self.calls = []

    def controller(self, proposer, evaluator=None, **options):
        return SupervisedController(
            self.store, evaluator_id="tests-v1",
            propose=proposer,
            evaluate=evaluator or (lambda value: EvaluatorResult(score=float(value))),
            **options)

    def test_requires_approval_before_any_user_code(self):
        controller = self.controller(lambda history, budget: self.fail("proposer invoked"),
                                     max_attempts=3, approval=False)
        with self.assertRaises(NykraError):
            controller.run(task="example", agent="test-agent")
        self.assertEqual(self.store.stats()["run_count"], 0)

    def test_evaluates_real_parent_links_and_stops(self):
        def proposer(observed, remaining):
            self.assertIsInstance(observed, tuple)
            self.assertEqual(remaining, 4 - len(observed))
            if not observed:
                return Proposal(1)
            if len(observed) == 1:
                return Proposal(4, parent_id=observed[0].attempt_id)
            return None
        run = self.controller(proposer, max_attempts=4, approval=True).run(
            task="branching", agent="host")
        self.assertEqual(run["attempt_count"], 2)
        self.assertEqual(run["stop_reason"], "proposer_finished")
        self.assertEqual(run["observations"][1]["parent_id"], run["observations"][0]["attempt_id"])
        self.assertEqual(run["observations"][1]["score"], 4)
        self.assertEqual(self.store.stats()["attempt_count"], 2)
        self.assertEqual(self.store.stats()["activity_count"], 0)

    def test_parent_must_be_observed_before_evaluating(self):
        def proposer(observed, remaining):
            return Proposal({"secret": "PRIVATE"}, parent_id="made-up-id")
        controller = self.controller(proposer, evaluator=lambda _: self.fail("should not evaluate"),
                                     max_attempts=2, approval=True)
        with self.assertRaises(NykraError):
            controller.run(task="invalid parent", agent="host")
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_candidate_and_evaluator_error_never_persist(self):
        control = self.controller(
            lambda observed, remaining: Proposal({"private_prompt": "SECRET_PAYLOAD"}),
            evaluator=lambda candidate: (_ for _ in ()).throw(RuntimeError("PASSWORD VALUE")),
            max_attempts=1, approval=True,
        )
        result = control.run(task="do not leak", agent="trusted")
        self.assertEqual(result["observations"][0]["status"], "failed")
        self.assertNotIn("PASSWORD", str(result))
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("PRIVATE", str(self.store.list_attempts(result["run_id"])))

    def test_proposer_exception_is_sanitized(self):
        def unsafe(*args):
            raise RuntimeError("SECRET_AGENT_PROMPT")
        with self.assertRaises(NykraError) as context:
            self.controller(unsafe, approval=True).run(task="oops", agent="host")
        self.assertNotIn("SECRET", str(context.exception))

    def test_count_budget_enforced_even_if_proposer_never_stops(self):
        result = self.controller(lambda observed, remaining: Proposal(1),
                                 approval=True, max_attempts=3).run(task="cap", agent="host")
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertEqual(self.store.stats()["attempt_count"], 3)

    def test_reject_bad_limits(self):
        with self.assertRaises(NykraError):
            self.controller(lambda *_: Proposal(1), approval=True, max_attempts=0)
        with self.assertRaises(NykraError):
            self.controller(lambda *_: Proposal(1), approval=True, max_seconds=float("inf"))


if __name__ == "__main__":
    unittest.main()
