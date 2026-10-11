"""Feedback-driven, externally proposed coding sessions with persistent state."""
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.iterative import IterativeCoding
from nykra.prospective import ProspectiveExperiment
from nykra.relai_coding import EVALUATOR_ID
from nykra.store import HistoryStore, NykraError

WRONG = "def solve(values):\n    return sorted(values)\n"
ANOTHER = "def solve(values):\n    return list(set(values))\n"
CORRECT = "def solve(values):\n    return sorted(set(values))\n"

class FeedbackLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nykra-iterative-test-")
        self.addCleanup(self.tmp.cleanup)
        self.store = HistoryStore(self.tmp.name)
        self.loop = IterativeCoding(self.store)

    def start(self, **opts):
        return self.loop.start(task_id="unique-sorted", policy=opts.get("policy", "depth"),
                               budget=opts.get("budget", 4), max_seconds=opts.get("max_seconds", 180),
                               approval=True)

    def test_approval_required_before_any_new_run_or_candidate(self):
        with self.assertRaises(NykraError):
            self.loop.start(task_id="unique-sorted", approval=False)
        self.assertEqual(self.store.stats()["run_count"], 0)
        session = self.start()
        with self.assertRaises(NykraError):
            self.loop.submit(session["session_id"], source=CORRECT)
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_model_proposes_revision_only_after_feedback(self):
        session = self.start(policy="depth", budget=3)
        sid = session["session_id"]
        self.assertEqual(session["request"]["kind"], "new_root")
        first = self.loop.submit(sid, source=WRONG, approval=True)
        self.assertLess(first["feedback"]["score"], 1)
        self.assertGreater(len(first["feedback"]["failure_examples"]), 0)
        self.assertEqual(first["request"]["kind"], "revise")
        self.assertEqual(first["request"]["parent_attempt_id"], first["evaluated_attempt_id"])
        revision = self.loop.submit(sid, source=CORRECT, approval=True)
        self.assertEqual(revision["feedback"]["score"], 1)
        self.assertIsNone(revision["request"])
        self.assertEqual(revision["best_training_score"], 1)
        finished = self.loop.finish(sid, best_source=CORRECT, approval=True)
        self.assertEqual(finished["state"], "finished")
        self.assertEqual(finished["final_score"], 1)
        self.assertEqual(self.store.stats()["attempt_count"], 2)
        attempts = self.store.list_attempts(finished["run_id"])
        self.assertEqual(attempts[1]["parent_id"], attempts[0]["id"])
        with self.assertRaises(NykraError):
            self.loop.submit(sid, source=CORRECT, approval=True)

    def test_reopen_after_restart_without_source_persistence(self):
        sid = self.start()["session_id"]
        self.loop.submit(sid, source=WRONG, approval=True)
        resumed = IterativeCoding(HistoryStore(self.tmp.name)).status(sid)
        self.assertEqual(resumed["evaluations_used"], 1)
        self.assertEqual(resumed["request"]["kind"], "revise")
        raw = Path(self.tmp.name, "iterative.sqlite3").read_bytes()
        self.assertNotIn(b"def solve", raw)
        self.assertNotIn(b"return sorted", raw)
        self.assertEqual(len(resumed["previous_feedback"]["failure_examples"]) > 0, True)

    def test_breadth_requests_second_root_before_revision(self):
        sid = self.start(policy="breadth", budget=4)["session_id"]
        first = self.loop.submit(sid, source=WRONG, approval=True)
        self.assertEqual(first["request"]["kind"], "new_root")
        second = self.loop.submit(sid, source=ANOTHER, approval=True)
        self.assertEqual(second["request"]["kind"], "revise")
        self.assertEqual(second["request"]["parent_attempt_id"], first["evaluated_attempt_id"])
        third = self.loop.submit(sid, source=CORRECT, approval=True)
        self.assertEqual(third["best_training_score"], 1)
        self.assertIsNone(third["request"])

    def test_no_heldout_leak_until_explicit_finish(self):
        sid = self.start()["session_id"]
        status = self.loop.submit(sid, source=WRONG, approval=True)
        self.assertNotIn("heldout_score", json.dumps(status))
        self.assertIsNone(status["final_score"])
        with self.assertRaises(NykraError):
            self.loop.finish(sid, best_source=CORRECT, approval=True)
        correct = self.loop.submit(sid, source=CORRECT, approval=True)
        self.assertTrue(correct["ready_to_finish"])
        final = self.loop.finish(sid, best_source=CORRECT, approval=True)
        self.assertEqual(final["final_score"], 1)

    def test_invalid_code_and_time_budget(self):
        sid = self.start(budget=2)["session_id"]
        with self.assertRaises(NykraError):
            self.loop.submit(sid, source="import os\ndef solve(x): return x", approval=True)
        self.assertEqual(self.store.stats()["attempt_count"], 0)
        with self.loop._db() as conn:
            conn.execute("UPDATE sessions SET started_at=? WHERE id=?",
                         (time.time()-10000, sid))
        with self.assertRaises(NykraError):
            self.loop.submit(sid, source=WRONG, approval=True)

    def test_abort_marks_session_terminal(self):
        sid = self.start()["session_id"]
        self.loop.submit(sid, source=WRONG, approval=True)
        result = self.loop.abort(sid, approval=True)
        self.assertEqual(result["state"], "aborted")
        self.assertEqual(result["terminal_status"], "failed")
        with self.assertRaises(NykraError):
            self.loop.abort(sid, approval=True)

    def test_prospective_assignment_is_real_and_finalized(self):
        experiment = ProspectiveExperiment(self.store)
        trial = experiment.create(evaluator_id=EVALUATOR_ID, objective="maximize",
                                  threshold=1, challenger="depth", attempt_budget=2,
                                  seconds_budget=180, approval=True)
        with patch("nykra.prospective.secrets.randbelow", return_value=1):
            session = self.loop.start(task_id="unique-sorted", policy="breadth",
                                      budget=2, max_seconds=180, threshold=1,
                                      trial_id=trial["id"], task_key="unique-task-for-v10",
                                      approval=True)
        self.assertEqual(session["policy"], "depth")
        sid = session["session_id"]
        self.loop.submit(sid, source=WRONG, approval=True)
        self.loop.submit(sid, source=CORRECT, approval=True)
        finished = self.loop.finish(sid, best_source=CORRECT, approval=True)
        self.assertEqual(finished["final_score"], 1)
        outcome = experiment.report(trial["id"])
        self.assertEqual(outcome["arms"]["depth"]["passes"], 1)
        self.assertEqual(outcome["state_of_evidence"], "not_ready")

    def test_prospective_abort_records_failed_assignment(self):
        experiment = ProspectiveExperiment(self.store)
        trial = experiment.create(evaluator_id=EVALUATOR_ID, objective="maximize",
                                  threshold=1, challenger="adaptive", attempt_budget=2,
                                  seconds_budget=180, approval=True)
        session = self.loop.start(task_id="unique-sorted",
                                  budget=2, max_seconds=180, threshold=1,
                                  trial_id=trial["id"], task_key="another-unique-id",
                                  approval=True)
        self.loop.abort(session["session_id"], approval=True)
        report = experiment.report(trial["id"])
        failures = sum(a["failures_or_violations"] for a in report["arms"].values())
        self.assertEqual(failures, 1)

    def test_adaptive_prefers_best_parent(self):
        sid = self.start(policy="adaptive", budget=4)["session_id"]
        first = self.loop.submit(sid, source=ANOTHER, approval=True)
        second = self.loop.submit(sid, source=WRONG, approval=True)
        self.assertEqual(second["request"]["kind"], "revise")
        best = max([first, second], key=lambda s:s["feedback"]["score"])
        self.assertEqual(second["request"]["parent_attempt_id"], best["evaluated_attempt_id"])

if __name__=="__main__":
    unittest.main()
