"""Regression benchmark invariants, independent of any remote model call."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.repository_repair_trial import (
    REGRESSIONS, expected_outcomes, extract_function, replace_function,
    model_prompt, prepare_repository, grade, protocol, execute_task
)


class RepoRepairTests(unittest.TestCase):
    def test_tasks_frozen_and_counterbalanced(self):
        doc = protocol()
        self.assertEqual(len(doc["tasks"]), 6)
        self.assertEqual(doc["max_model_turns_per_task_arm"], 2)
        self.assertEqual(sum(t["order"][0] == "baseline" for t in doc["tasks"]), 3)
        self.assertEqual(set(REGRESSIONS), {t["id"] for t in doc["tasks"]})
        for task in doc["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual(sorted(task["order"]), ["baseline", "nykra"])
                public, _ = expected_outcomes(task["id"],heldout=False)
                unseen, _ = expected_outcomes(task["id"],heldout=True)
                self.assertEqual(len(public), 7)
                self.assertEqual(len(unseen), 26)

    def test_legal_and_illegal_function_patch(self):
        source = "import math\n\n\ndef solve(x):\n    return 3\n\n\ndef other(y):\n    return y\n"
        result = replace_function(source,"solve","def solve(x):\n    return x + 2\n")
        self.assertIn("return x + 2",extract_function(result,"solve"))
        self.assertIn("def other(y)",result)
        for invalid in ("def wrong(x): return x", "import os\ndef solve(x): return x",
                        "def solve(x): return x\ndef other(x): return x"):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                replace_function(source,"solve",invalid)

    def test_both_arms_get_same_first_prompt_and_public_feedback(self):
        task = protocol()["tasks"][0]
        sample = "def test(a,b): return a+b\n"
        first_base = model_prompt(task,sample,prev=None,arm="baseline")
        first_guided = model_prompt(task,sample,prev=None,arm="nykra")
        self.assertEqual(first_base,first_guided)
        feedback = {"source":sample,"public":{"passed":2,"total":7,"failed_public":[{"inputs":[0,1],"expected":{"value":1.0},"observed":{"value":0.}}]},"error":None}
        base = model_prompt(task,sample,prev=feedback,arm="baseline")
        guided = model_prompt(task,sample,prev=feedback,arm="nykra")
        self.assertIn(sample,base)
        self.assertIn(sample,guided)
        self.assertIn("failed_public",base)
        self.assertIn("failed_public",guided)
        self.assertIn("BASELINE POLICY",base)
        self.assertIn("NYKRA POLICY",guided)

    def test_stored_result_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"existing.json"
            with self.assertRaises(ValueError):
                execute_task("pvalue-tail",path)
            path.write_text("preserve")
            with self.assertRaises(ValueError):
                execute_task("pvalue-tail",path,approval=True)
            self.assertEqual(path.read_text(),"preserve")

    def test_real_checkout_mutation_and_hidden_grading(self):
        task = next(x for x in protocol()["tasks"] if x["id"]=="pvalue-tail")
        with tempfile.TemporaryDirectory(prefix="nykra-repo-test-") as directory:
            path=Path(directory)
            good=prepare_repository(task,path,mutate=False)
            bad=prepare_repository(task,path,mutate=True)
            self.assertEqual(grade(good,task,heldout=True)["score"],1)
            self.assertLess(grade(bad,task,heldout=True)["score"],1)


if __name__=="__main__":
    unittest.main()
