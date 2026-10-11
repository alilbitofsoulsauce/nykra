"""Prospective task randomization and predeclared evaluation gates."""
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from nykra.evaluation import EvaluatorResult
from nykra.prospective import ExecutionResult, ProspectiveExperiment
from nykra.store import HistoryStore, NykraError


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nykra-trial-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = HistoryStore(self.home)
        self.manager = ProspectiveExperiment(self.store)

    def create(self, **kwargs):
        return self.manager.create(
            evaluator_id="metric-v1", objective="maximize", threshold=0.5,
            challenger="depth", attempt_budget=3, seconds_budget=10,
            max_tasks=100, min_per_arm=10, approval=True, **kwargs)

    def run_sample(self, trial_id, key, *, execute=None, evaluate=None):
        return self.manager.run_task(
            trial_id=trial_id, task_key=key, task={"private": "SECRET_PROMPT"},
            execute=execute or (lambda policy, task, budget, seconds:
                                ExecutionResult(candidate=1 if policy == "depth" else 0,
                                                attempts_used=2, cost_units=2)),
            evaluate=evaluate or (lambda task, candidate: EvaluatorResult(float(candidate))),
            approval=True)

    def test_creation_requires_explicit_approval(self):
        with self.assertRaises(NykraError):
            self.manager.create(evaluator_id="metric-v1", objective="maximize",
                                threshold=0.5, challenger="depth")
        self.assertTrue(self.manager.database.exists())  # schema may exist even without trials
        with self.manager._db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0], 0)

    def test_assignment_is_persisted_before_host_execution(self):
        trial = self.create()
        def check(policy, task, budget, seconds):
            with self.manager._db() as conn:
                rows = conn.execute("SELECT state, policy FROM assignments").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["state"], "running")
                self.assertEqual(rows[0]["policy"], policy)
            return ExecutionResult(candidate=1.0, attempts_used=budget)
        result = self.run_sample(trial["id"], "task-a", execute=check)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["passed"])
        self.assertNotIn("SECRET", self.manager.database.read_bytes().decode("utf-8",errors="ignore"))
        self.assertNotIn("task-a", self.manager.database.read_bytes().decode("utf-8",errors="ignore"))

    def test_duplicate_task_never_reexecuted(self):
        trial = self.create()
        allocation = self.manager.assign(trial_id=trial["id"], task_key="task-a")
        again = self.manager.assign(trial_id=trial["id"], task_key="task-a")
        self.assertEqual(again["assignment_id"], allocation["assignment_id"])
        self.run_sample(trial["id"], "task-a")
        with self.assertRaises(NykraError):
            self.run_sample(trial["id"], "task-a", execute=lambda *_: self.fail("re-executed"))
        self.assertEqual(self.manager.report(trial["id"])["assigned_count"], 1)

    def test_assignment_atomic_across_concurrent_hosts(self):
        trial = self.create()
        def assign():
            return self.manager.assign(trial_id=trial["id"], task_key="same-task")["assignment_id"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            values = list(pool.map(lambda _: assign(), range(12)))
        self.assertEqual(len(set(values)), 1)
        self.assertEqual(self.manager.report(trial["id"])["assigned_count"], 1)

    def test_cannot_close_with_pending_or_running_and_failure_counts(self):
        trial = self.create()
        pending = self.manager.assign(trial_id=trial["id"], task_key="lost")
        with self.assertRaises(NykraError):
            self.manager.close(trial["id"])
        marked = self.manager.finish(trial_id=trial["id"], assignment_id=pending["assignment_id"],
                                     status="failed")
        self.assertFalse(marked["passed"])
        self.assertEqual(self.manager.close(trial["id"])["state"], "closed")
        report = self.manager.report(trial["id"])
        self.assertEqual(report["state_of_evidence"], "not_ready")
        self.assertEqual(report["assigned_count"], 1)
        self.assertEqual(sum(x["failures_or_violations"] for x in report["arms"].values()), 1)
        with self.assertRaises(NykraError):
            self.manager.assign(trial_id=trial["id"], task_key="brand-new")

    def test_attempt_budget_exceeded_is_failure_not_exclusion(self):
        trial = self.create()
        result = self.run_sample(trial["id"], "overbudget", execute=lambda policy, task, budget, secs:
                          ExecutionResult(candidate=0.99, attempts_used=budget+1))
        self.assertEqual(result["status"], "budget_violation")
        self.assertFalse(result["passed"])
        report = self.manager.report(trial["id"])
        self.assertEqual(report["assigned_count"], 1)
        self.assertEqual(sum(x["passes"] for x in report["arms"].values()), 0)

    def test_evaluator_exception_is_sanitized_and_counted_as_failure(self):
        trial = self.create()
        result = self.run_sample(trial["id"], "bad-evaluator",
                          evaluate=lambda *_: (_ for _ in ()).throw(RuntimeError("SECRET_KEY")))
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("SECRET", json.dumps(result))
        with self.manager._db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM assignments WHERE state='failed'").fetchone()[0], 1)

    def test_reporting_does_not_peek_while_open(self):
        trial = self.create()
        with patch("nykra.prospective.secrets.randbelow", side_effect=[0,1]*30):
            for i in range(40):
                self.run_sample(trial["id"], "t" + str(i))
        active = self.manager.report(trial["id"])
        self.assertEqual(active["state_of_evidence"], "not_ready")
        self.assertIsNone(active["fisher_one_sided_p"])
        self.manager.close(trial["id"])
        finished = self.manager.report(trial["id"])
        self.assertEqual(finished["state_of_evidence"], "advisory_candidate")
        self.assertFalse(finished["can_auto_apply"])
        self.assertEqual(finished["candidate_policy"], "depth")
        self.assertLessEqual(finished["fisher_one_sided_p"], .05)
        self.assertEqual(finished["arms"]["breadth"]["assigned"], 20)
        self.assertEqual(finished["arms"]["depth"]["assigned"], 20)

    def test_no_effect_stays_baseline(self):
        trial = self.create()
        with patch("nykra.prospective.secrets.randbelow", side_effect=[0,1]*30):
            for i in range(40):
                self.run_sample(trial["id"], "t" + str(i),
                         execute=lambda policy, task, budget, seconds: ExecutionResult(1,2))
        self.manager.close(trial["id"])
        result = self.manager.report(trial["id"])
        self.assertEqual(result["state_of_evidence"], "hold_baseline")
        self.assertIsNone(result["candidate_policy"])
        self.assertEqual(result["challenger_minus_baseline_success_rate"], 0)

    def test_minimize_objective_and_threshold(self):
        trial = self.manager.create(evaluator_id="metric-v1", objective="minimize",
                                    threshold=0.5, challenger="adaptive", approval=True)
        with patch("nykra.prospective.secrets.randbelow", return_value=1):
            result = self.run_sample(trial["id"], "low",
                              execute=lambda policy, task, budget, sec: ExecutionResult(.2,1))
        self.assertTrue(result["passed"])
        self.assertEqual(self.manager.report(trial["id"])["arms"]["adaptive"]["passes"], 1)

    def test_closed_trial_cannot_overwrite_outcome(self):
        trial = self.create()
        outcome = self.run_sample(trial["id"], "task-1")
        with self.assertRaises(NykraError):
            self.manager.finish(trial_id=trial["id"], assignment_id=outcome["assignment_id"],
                                status="failed")
        with self.manager._db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0], 1)

    def test_separate_history_database_compatible_with_existing_observer(self):
        trial = self.create()
        self.run_sample(trial["id"], "task")
        self.assertEqual(self.store.stats()["schema_version"], 2)
        self.assertEqual(self.store.stats()["run_count"], 0)
        self.assertEqual(self.store.stats()["attempt_count"], 0)
        self.assertEqual(self.store.stats()["activity_count"], 0)
        self.assertTrue((self.home / "prospective.sqlite3").is_file())

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(NykraError):
            self.manager.create(evaluator_id="metric-v1", objective="maximize",
                                threshold=1, challenger="breadth", approval=True)
        trial = self.create()
        with self.assertRaises(NykraError):
            self.manager.assign(trial_id=trial["id"], task_key="user private prompt")
        with self.assertRaises(NykraError):
            self.manager.finish(trial_id=trial["id"], assignment_id="nonesuch",
                                status="completed", score=1, attempts_used=1, elapsed_ms=1)


if __name__ == "__main__":
    unittest.main()
