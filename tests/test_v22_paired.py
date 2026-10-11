"""v0.22 paired experiment: strict shared inference prefix, real Git patch paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import agent_workflow as wf
from nykra import v22_paired
from nykra.v21_grader import function_at, manifest

class PairedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p=patch.object(wf,"SESSIONS",Path(self.tmp.name)/"sessions")
        p.start()
        self.addCleanup(p.stop)
        task=next(t for t in manifest()[0]["tasks"] if t["id"]=="youtube-dl-43")
        self.correct_source=function_at(task,task["fixed_commit"])

    def test_shared_first_inference_and_real_patch_both_branches(self):
        prompts=[]
        def model(prompt, seconds):
            prompts.append(prompt)
            return {"status":"ok","source":self.correct_source,"tokens":6,"seconds":0.1}
        with patch.object(wf,"grade",return_value={"status":"ok","passed":True}):
            out=v22_paired.run_pair("youtube-dl-43",provider=model,approve=True)
        self.assertEqual(len(prompts),1)
        self.assertEqual(out["shared_model_completion_count"],1)
        self.assertIsNone(out["policy_divergence"])
        for arm in ("depth","adaptive"):
            r=out["results"][arm]
            self.assertTrue(r["full_success"])
            self.assertEqual(r["tested_git_patches"],1)
            self.assertEqual(r["attempt_count"],1)
        self.assertFalse(out["causal_or_general_uplift_proven"])

    def test_genuine_policy_divergence_after_three_shared_failed_git_patches(self):
        prompts=[]
        def model(prompt, seconds):
            prompts.append(prompt)
            return {"status":"ok","source":self.correct_source,"tokens":2,"seconds":0.1}
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            out=v22_paired.run_pair("youtube-dl-43",provider=model,approve=True)
        self.assertEqual(out["shared_model_completion_count"],3)
        self.assertEqual(out["total_model_completions"],5)
        divergence=out["policy_divergence"]
        self.assertIsNotNone(divergence)
        self.assertEqual(divergence["depth_action"]["kind"],"revise")
        self.assertEqual(divergence["adaptive_action"]["kind"],"new_root")
        for arm in ("depth","adaptive"):
            r=out["results"][arm]
            self.assertEqual(r["attempt_count"],4)
            self.assertEqual(r["tested_git_patches"],4)
            self.assertFalse(r["full_success"])
        # Three calls once each, then two independent continuations.
        self.assertEqual(len(prompts),5)

    def test_unregistered_task_and_missing_approval_blocked(self):
        with self.assertRaisesRegex(ValueError,"authorization"):
            v22_paired.run_pair("youtube-dl-27")
        with self.assertRaisesRegex(ValueError,"frozen"):
            v22_paired.run_pair("youtube-dl-24",provider=lambda *_:None,approve=True)

if __name__=="__main__":
    unittest.main()
