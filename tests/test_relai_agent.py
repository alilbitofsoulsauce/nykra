"""Rel.AI-first agent driver regression and end-to-end tests."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.relai_agent import RelaiAgent
from nykra.relai_coding import EVALUATOR_ID, evaluate_source
from nykra.prospective import ProspectiveExperiment
from nykra.store import HistoryStore, NykraError

BAD = "def solve(values):\n    return sorted(values)\n"
OTHER = "def solve(values):\n    return list(set(values))\n"
GOOD = "def solve(values):\n    return sorted(set(values))\n"


class RelaiAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nykra-relai-driver-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = HistoryStore(self.home)
        self.agent = RelaiAgent(self.store)

    def start(self, **params):
        return self.agent.start(task_id="unique-sorted",
                                policy=params.get("policy", "depth"),
                                budget=params.get("budget", 3),
                                max_seconds=120, approval=True)

    def test_approval_required_and_does_not_create_unapproved_run(self):
        with self.assertRaises(NykraError):
            self.agent.start(task_id="unique-sorted")
        self.assertEqual(self.store.stats()["run_count"], 0)
        started = self.start()
        with self.assertRaises(NykraError):
            self.agent.submit(started["session"]["session_id"], source=BAD)
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_live_feedback_revision_and_automatic_heldout_finalization(self):
        init = self.start(budget=3)
        sid = init["session"]["session_id"]
        self.assertEqual(init["request"]["kind"], "new_root")
        self.assertFalse(init["model_invocation"])
        first = self.agent.submit(sid, source=BAD, approval=True)
        self.assertEqual(first["state"], "awaiting_agent")
        self.assertLess(first["evaluated"]["feedback"]["score"], 1.0)
        self.assertGreater(len(first["next"]["session"]["previous_feedback"]["failure_examples"]), 0)
        self.assertEqual(first["next"]["request"]["kind"], "revise")
        self.assertEqual(first["next"]["parent_source"], BAD)
        answer = self.agent.submit(sid, source=GOOD, approval=True)
        self.assertEqual(answer["state"], "finished")
        self.assertEqual(answer["heldout_score"], 1.0)
        self.assertTrue(answer["source_cache_cleared"])
        self.assertEqual(answer["attempts_used"], 2)
        self.assertEqual(self.agent.loop.status(sid)["state"], "finished")
        cache = self.agent._folder(sid)
        self.assertEqual(list(cache.glob("*.py")), [])
        with self.assertRaises(NykraError):
            self.agent.submit(sid, source=GOOD, approval=True)
        attempts = self.store.list_attempts(answer["session"]["run_id"])
        self.assertEqual(attempts[1]["parent_id"], attempts[0]["id"])

    def test_best_candidate_finalized_even_when_last_candidate_worse(self):
        started = self.start(policy="breadth", budget=2)
        sid = started["session"]["session_id"]
        self.agent.submit(sid, source=BAD, approval=True)
        answer = self.agent.submit(sid, source=OTHER, approval=True)
        self.assertEqual(answer["state"], "finished")
        selected_best = BAD if evaluate_source("unique-sorted", BAD, heldout=False) >= (
            evaluate_source("unique-sorted", OTHER, heldout=False)) else OTHER
        self.assertEqual(answer["heldout_score"], evaluate_source(
            "unique-sorted", selected_best, heldout=True))
        self.assertTrue(answer["source_cache_cleared"])

    def test_recovers_across_new_host_instances(self):
        sid = self.start()["session"]["session_id"]
        self.agent.submit(sid, source=BAD, approval=True)
        fresh = RelaiAgent(HistoryStore(self.home))
        resumed = fresh.next(sid)
        self.assertEqual(resumed["parent_source"], BAD)
        completed = fresh.submit(sid, source=GOOD, approval=True)
        self.assertEqual(completed["heldout_score"], 1.0)

    def test_explicit_abort_clears_cached_sources(self):
        sid = self.start()["session"]["session_id"]
        self.agent.submit(sid, source=BAD, approval=True)
        done = self.agent.abort(sid, approval=True)
        self.assertEqual(done["state"], "aborted")
        self.assertEqual(list(self.agent._folder(sid).glob("*.py")), [])
        with self.assertRaises(NykraError):
            self.agent.abort(sid, approval=True)

    def test_invalid_source_does_not_consume_budget(self):
        sid = self.start()["session"]["session_id"]
        with self.assertRaises(NykraError):
            self.agent.submit(sid, source="import os\ndef solve(x): return x", approval=True)
        self.assertEqual(self.agent.next(sid)["session"]["evaluations_used"], 0)

    def test_tampered_source_cache_does_not_exfiltrate(self):
        sid = self.start()["session"]["session_id"]
        self.agent.submit(sid, source=BAD, approval=True)
        file = self.agent._folder(sid) / "OWNER"
        file.write_text("not-nykra", encoding="ascii")
        with self.assertRaises(NykraError):
            self.agent.next(sid)

    def test_cache_paths_refuse_traversal(self):
        for illegal in ("../other", "..", "session/child", "A"*32, "hello"):
            with self.subTest(id=illegal), self.assertRaises(NykraError):
                self.agent.next(illegal)
        sid = self.start()["session"]["session_id"]
        with self.assertRaises(NykraError):
            self.agent._source_file(self.agent._folder(sid), "../outside")
        self.agent.abort(sid, approval=True)

    def test_prospective_assignment_and_auto_result(self):
        trial_engine = ProspectiveExperiment(self.store)
        trial = trial_engine.create(
            evaluator_id=EVALUATOR_ID, objective="maximize",
            threshold=1.0, challenger="depth",
            attempt_budget=2, seconds_budget=120,
            approval=True)
        with patch("nykra.prospective.secrets.randbelow", return_value=1):
            init = self.agent.start(task_id="unique-sorted",
                                    budget=2, max_seconds=120,
                                    threshold=1, trial_id=trial["id"],
                                    task_key="fresh-task-1", approval=True)
        self.assertEqual(init["session"]["policy"], "depth")
        sid = init["session"]["session_id"]
        self.agent.submit(sid, source=BAD, approval=True)
        finished = self.agent.submit(sid, source=GOOD, approval=True)
        self.assertEqual(finished["heldout_score"], 1.0)
        self.assertEqual(trial_engine.report(trial["id"])["arms"]["depth"]["passes"], 1)
        self.assertFalse(trial_engine.report(trial["id"])["can_auto_apply"])

    def test_cli_end_to_end_with_isolated_home(self):
        project = Path(__file__).resolve().parents[1]
        def cli(*argv):
            r = subprocess.run(
                [sys.executable, "-m", "nykra", "--home", str(self.home), "relai-agent", *argv],
                cwd=project, capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, r.stdout + "\n" + r.stderr)
            return json.loads(r.stdout)
        created = cli("start", "--task", "unique-sorted",
                      "--budget", "2", "--max-seconds", "120", "--approve")
        sid = created["session"]["session_id"]
        first_source = self.home / "candidate1.py"
        second_source = self.home / "candidate2.py"
        first_source.write_text(BAD)
        second_source.write_text(GOOD)
        first = cli("submit", "--session", sid, "--candidate-file", str(first_source), "--approve")
        self.assertEqual(first["next"]["parent_source"], BAD)
        resumed = cli("next", "--session", sid)
        self.assertEqual(resumed["request"]["kind"], "revise")
        finished = cli("submit", "--session", sid, "--candidate-file", str(second_source), "--approve")
        self.assertEqual(finished["heldout_score"], 1)
        self.assertEqual(finished["state"], "finished")
        first_source.unlink()
        second_source.unlink()


if __name__ == "__main__":
    unittest.main()
