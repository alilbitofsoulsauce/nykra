"""Coding study fixtures and evaluator integrity tests."""
import json
import tempfile
import unittest
from pathlib import Path

from nykra.coding_study import evaluate_frozen_candidates
from nykra.study_tasks import TASKS,cases,oracle
from nykra.relai_coding import evaluate_source
from nykra.store import NykraError

BAD_CONTROLS={
    "unique-window":"def solve(text):\n    return len(text)\n",
    "maximum-subarray":"def solve(values):\n    return sum(values)\n",
    "min-cover-window":"def solve(text, required):\n    return text\n",
    "nonoverlap-intervals":"def solve(intervals):\n    return len(intervals)\n",
    "trapped-water":"def solve(heights):\n    return 0\n",
    "next-greater":"def solve(values):\n    return [-1] * len(values)\n",
    "common-prefix":"def solve(words):\n    return words[0] if words else ''\n",
    "subsequence-count":"def solve(text, pattern):\n    return 0\n",
}


class CodingStudyTests(unittest.TestCase):
    def test_separate_deterministic_training_and_heldout_sets(self):
        self.assertEqual(set(TASKS),set(BAD_CONTROLS))
        for task in TASKS:
            with self.subTest(task=task):
                train=cases(task,heldout=False)
                hold=cases(task,heldout=True)
                self.assertEqual(len(train),18)
                self.assertEqual(len(hold),40)
                self.assertEqual(train,cases(task,heldout=False))
                self.assertNotEqual(train[:3],hold[:3])
                train_keys={json.dumps(arguments,sort_keys=True) for arguments,_ in train}
                heldout_keys={json.dumps(arguments,sort_keys=True) for arguments,_ in hold}
                self.assertTrue(train_keys.isdisjoint(heldout_keys))
                self.assertEqual(len(heldout_keys),40)
                for args,expected in train+hold:
                    self.assertEqual(oracle(task,*args),expected)

    def test_evaluator_rejects_known_wrong_control_on_every_task(self):
        for task,bad in BAD_CONTROLS.items():
            with self.subTest(task=task):
                self.assertLess(evaluate_source(task,bad,heldout=False),1.0)
                self.assertLess(evaluate_source(task,bad,heldout=True),1.0)

    def test_frozen_real_model_candidates_are_reproducible(self):
        manifest=Path(__file__).resolve().parents[1]/"docs/evidence/v13_model_authored_first_attempts.json"
        self.assertTrue(manifest.is_file())
        report=evaluate_frozen_candidates(manifest,approval=True)
        self.assertEqual(report["task_family_count"],8)
        self.assertEqual(report["heldout_test_cases"],320)
        self.assertEqual(report["heldout_test_cases_passed"],320)
        self.assertEqual(report["first_attempt_tasks_passed"],8)
        self.assertFalse(report["study_limits"]["real_model_gain_proven"])

    def test_manifest_approval_required_and_extraneous_tasks_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"candidates.json"
            file.write_text(json.dumps({"other":"def solve(x): return x"}))
            with self.assertRaises(NykraError):
                evaluate_frozen_candidates(file,approval=False)
            with self.assertRaises(NykraError):
                evaluate_frozen_candidates(file,approval=True)


if __name__=="__main__":
    unittest.main()
