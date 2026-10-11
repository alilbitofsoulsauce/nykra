"""Real Python candidate evaluation under Rel.AI-mediated supervised policies."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.coding_worker import validate_source
from nykra.relai_coding import (EVALUATOR_ID, available_tasks, evaluate_source,
                                run_proposal_trial)
from nykra.prospective import ProspectiveExperiment
from nykra.store import HistoryStore, NykraError

BAD="def solve(values):\n    return sorted(values)\n"
GOOD="def solve(values):\n    return sorted(set(values))\n"
UNSORTED="def solve(values):\n    return list(set(values))\n"
BALANCED="""def solve(text):
    stack = []
    opens = "([{"
    closes = ")]}"
    for ch in text:
        if ch in opens:
            stack.append(ch)
        elif ch in closes:
            if not stack or opens.index(stack[-1]) != closes.index(ch):
                return False
            stack.pop()
    return len(stack) == 0
"""
# For the restricted worker, use a dictionary rather than str.index (attributes forbidden).
BALANCED= """def solve(text):
    stack = []
    matches = {")":"(","]":"[","}":"{"}
    for ch in text:
        if ch in "([{":
            stack = stack + [ch]
        elif ch in ")]}":
            if not stack:
                return False
            if stack[-1] != matches[ch]:
                return False
            stack = stack[:-1]
    return len(stack) == 0
"""


class CodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=HistoryStore(self.tmp.name)
        self.experiment=ProspectiveExperiment(self.store)
    def trial(self):
        return self.experiment.create(
            evaluator_id=EVALUATOR_ID, objective="maximize",threshold=1.0,
            challenger="depth",attempt_budget=2,seconds_budget=30,
            max_tasks=40,min_per_arm=10,approval=True)

    def pool(self):
        return {"task_id":"unique-sorted","proposals":[
            {"id":"first-root","parent_id":None,"source":BAD},
            {"id":"first-child","parent_id":"first-root","source":GOOD},
            {"id":"second-root","parent_id":None,"source":UNSORTED},
            {"id":"second-child","parent_id":"second-root","source":GOOD},
        ]}

    def test_real_code_evaluator_distinguishes_correctness(self):
        self.assertEqual(evaluate_source("unique-sorted", GOOD),1.0)
        self.assertLess(evaluate_source("unique-sorted",BAD),1.0)
        self.assertEqual(evaluate_source("balanced-brackets",BALANCED),1.0)

    def test_prohibits_imports_filesystem_and_introspection(self):
        invalid=["import os\ndef solve(x):\n return x",
                 "def solve(x):\n return open(x)",
                 "def solve(x):\n return x.__class__",
                 "def solve(x):\n return eval(x)",
                 "def solve(x):\n while True:\n  pass"]
        for candidate in invalid:
            with self.subTest(candidate=candidate),self.assertRaises((ValueError,SyntaxError)):
                validate_source(candidate)

    def test_real_trial_follows_assigned_frontier_and_persists_scores_only(self):
        trial=self.trial()
        with patch("nykra.prospective.secrets.randbelow",return_value=1):
            depth=run_proposal_trial(self.store,trial_id=trial["id"],task_key="depth-1",
                                     pool=self.pool(),approval=True)
        self.assertEqual(depth["policy_assigned"],"depth")
        self.assertEqual([x["candidate_id"] for x in depth["attempts"]],
                         ["first-root","first-child"])
        self.assertTrue(depth["final_outcome"]["passed"])
        self.assertEqual(depth["final_outcome"]["score"],1.0)
        with patch("nykra.prospective.secrets.randbelow",return_value=0):
            breadth=run_proposal_trial(self.store,trial_id=trial["id"],task_key="breadth-1",
                                       pool=self.pool(),approval=True)
        self.assertEqual(breadth["policy_assigned"],"breadth")
        self.assertEqual([x["candidate_id"] for x in breadth["attempts"]],
                         ["first-root","second-root"])
        self.assertFalse(breadth["final_outcome"]["passed"])
        self.assertEqual(self.store.stats()["attempt_count"],4)
        self.assertEqual(self.store.stats()["run_count"],2)
        self.assertEqual(self.experiment.report(trial["id"])["state_of_evidence"],"not_ready")
        persisted=json.dumps(self.store.list_attempts(depth["run_id"]))
        self.assertNotIn("def solve",persisted)
        self.assertNotIn("return sorted",persisted)

    def test_rejects_pool_mutation_and_missing_approval_without_starting_trial(self):
        trial=self.trial()
        with self.assertRaises(NykraError):
            run_proposal_trial(self.store,trial_id=trial["id"],task_key="unauthorized",
                               pool=self.pool(),approval=False)
        bad=self.pool()
        bad["proposals"][1]["parent_id"]="unknown"
        with self.assertRaises(NykraError):
            run_proposal_trial(self.store,trial_id=trial["id"],task_key="bad",
                               pool=bad,approval=True)
        self.assertEqual(self.experiment.report(trial["id"])["assigned_count"],0)

    def test_duplicate_task_refuses_reexecution(self):
        trial=self.trial()
        run_proposal_trial(self.store,trial_id=trial["id"],task_key="same-task",
                           pool=self.pool(),approval=True)
        with self.assertRaises(NykraError):
            run_proposal_trial(self.store,trial_id=trial["id"],task_key="same-task",
                               pool=self.pool(),approval=True)
        self.assertEqual(self.experiment.report(trial["id"])["assigned_count"],1)

    def test_untrusted_candidate_failure_safely_scores_zero(self):
        # Infinite loop is terminated by the subprocess timeout; it cannot
        # corrupt the parent Nykra process.
        source="def solve(values):\n    for i in range(999999999):\n        pass\n    return values\n"
        self.assertEqual(evaluate_source("unique-sorted",source),0.0)

if __name__=="__main__":
    unittest.main()
