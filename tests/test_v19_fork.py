"""v0.19 controlled fork: no post-hoc task selection or mismatched prefix."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.v19_fork_trial import (
    _fork_prompt, _steps, continue_arm, fork_actions,
    make_shared_prefix, protocol, run_task,
)


def shared_failures():
    return [{
        "id": f"attempt-{i}", "kind": "new_root" if i == 1 else "revise",
        "parent_attempt_id": None if i == 1 else f"attempt-{i-1}",
        "source": f"def example(): return {i}",
        "source_sha256": f"hash-{i}",
        "model_status": "ok", "model_seconds": 1,
        "tokens_reported": 100,
        "public": {"status": "test_failed", "passed": False},
    } for i in range(1, 4)]


class ControlledForkTests(unittest.TestCase):
    def setUp(self):
        self.p, self.sha = protocol()
        self.task_id = "youtube-dl-20"
        self.task = next(t for t in
            __import__("nykra.real_issue_v18", fromlist=["manifest"]).manifest()[0]["tasks"]
            if t["id"] == self.task_id)
        self.broken = "def get_elements_by_attribute(attribute,value,html,escape_value=True):\n    return []\n"

    def test_frozen_population_and_shared_budget(self):
        self.assertEqual(len(self.p["task_ids"]),4)
        self.assertEqual(self.p["shared_prefix_attempts"],3)
        self.assertEqual(self.p["continuations_per_arm"],2)
        self.assertEqual(len(self.sha),64)
        self.assertEqual(set(self.p["arm_order"]),set(self.p["task_ids"]))

    def test_actual_policy_decision_diverges_only_at_fourth(self):
        a = fork_actions(shared_failures(),self.p)
        self.assertEqual(a["baseline"],
                         {"kind":"revise","parent_attempt_id":"attempt-3"})
        self.assertEqual(a["nykra"],
                         {"kind":"new_root","parent_attempt_id":None})

    def test_partial_or_infrastructure_failed_prefix_not_forkable(self):
        with self.assertRaises(ValueError):
            fork_actions(shared_failures()[:2],self.p)
        bad=shared_failures()
        bad[2]["public"]={"status":"timeout","passed":False}
        with self.assertRaises(ValueError):
            fork_actions(bad,self.p)

    def test_fork_prompts_common_issue_and_distinct_action(self):
        prefix=shared_failures()
        actions=fork_actions(prefix,self.p)
        root=_fork_prompt(self.task,self.broken,prefix,prefix,actions["nykra"])
        revise=_fork_prompt(self.task,self.broken,prefix,prefix,actions["baseline"])
        for p in (root,revise):
            self.assertIn(self.task["issue"],p)
            self.assertIn("SHARED ATTEMPTS",p)
            self.assertNotIn(self.task["fixed_commit"],p)
            for name in self.task["hidden_upstream_tests"]:
                self.assertNotIn(name,p)
        self.assertIn("independent new root",root)
        self.assertIn("SELECTED PARENT SOURCE",revise)
        self.assertNotIn("SELECTED PARENT SOURCE",root)

    def test_shared_prefix_is_not_duplicated_across_arms(self):
        calls=[]
        grades=[]
        def propose(prompt,timeout):
            calls.append(prompt)
            return {"status":"ok","source":self.broken,
                    "tokens":100,"seconds":1}
        def grade(task,*,mode,candidate=None):
            grades.append(mode)
            return {"status":"test_failed","passed":False}
        with patch("nykra.v19_fork_trial.grade",side_effect=grade):
            prefix,reason=make_shared_prefix(self.task,self.broken,self.p,
                                             proposer=propose)
            self.assertEqual(reason,"failed_prefix_ready")
            left=continue_arm(self.task,self.broken,prefix,self.p,"baseline",
                              proposer=propose)
            right=continue_arm(self.task,self.broken,prefix,self.p,"nykra",
                               proposer=propose)
        self.assertEqual(len(prefix),3)
        self.assertEqual(len(calls),7)   # common 3 + 2 + 2
        self.assertEqual(grades,["public"] * 7)
        self.assertEqual(left["common_prefix_sha256"],right["common_prefix_sha256"])
        self.assertEqual(left["first_action"]["kind"],"revise")
        self.assertEqual(right["first_action"]["kind"],"new_root")
        self.assertEqual(left["continuation_calls"],right["continuation_calls"])
        self.assertFalse(left["hidden_pass"])
        self.assertFalse(right["hidden_pass"])

    def test_stop_shared_success_without_arms_or_forced_fork(self):
        def propose(prompt,timeout):
            return {"status":"ok","source":self.broken,"tokens":10,"seconds":1}
        with patch("nykra.v19_fork_trial.grade",
                   return_value={"status":"ok","passed":True}):
            history,why=make_shared_prefix(self.task,self.broken,self.p,
                                           proposer=propose)
        self.assertEqual(why,"public_solved")
        self.assertEqual(len(history),1)

    def test_no_evidence_overwrite_or_implicit_approval(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/"result.json"
            with self.assertRaises(ValueError):
                run_task(self.task_id,output)
            output.write_text("original")
            with self.assertRaisesRegex(ValueError,"overwrite"):
                run_task(self.task_id,output,approve=True)
            self.assertEqual(output.read_text(),"original")

    def test_hidden_grade_only_after_public_success(self):
        prefix=shared_failures()
        seen=[]
        def propose(prompt,timeout):
            return {"status":"ok","source":self.broken,
                    "tokens":7,"seconds":1}
        def fake_grade(task,*,mode,candidate=None):
            seen.append(mode)
            return {"status":"ok","passed":True}
        with patch("nykra.v19_fork_trial.grade",side_effect=fake_grade):
            arm=continue_arm(self.task,self.broken,prefix,self.p,"nykra",
                             proposer=propose)
        self.assertEqual(seen,["public","hidden"])
        self.assertEqual(arm["continuation_calls"],1)
        self.assertTrue(arm["full_success"])


if __name__ == "__main__":
    unittest.main()
