"""v0.23 real Git/Docker public-evidence sharing: fail-closed receipt tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import agent_workflow as wf
from nykra.v21_grader import function_at, manifest


class VerifiedReuseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p=patch.object(wf, "SESSIONS", Path(temp.name)/"workflows")
        p.start()
        self.addCleanup(p.stop)
        task=next(t for t in manifest()[0]["tasks"] if t["id"]=="youtube-dl-43")
        self.reference=function_at(task,task["fixed_commit"])

    def make_pair(self,budget=4):
        a=wf.start(task_id="youtube-dl-43",policy="depth",budget=budget,approve=True)
        b=wf.start(task_id="youtube-dl-43",policy="adaptive",budget=budget,approve=True)
        self.assertEqual(a["prompt_sha256"],b["prompt_sha256"])
        return a,b

    def test_real_git_verified_public_result_is_shared_without_grader_calls(self):
        a,b=self.make_pair()
        events=[]
        def grader(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"test_failed","passed":False,
                    "diagnostic":"AssertionError: expected c.mp4"}
        with patch.object(wf,"grade",side_effect=grader):
            ran=wf.submit(a["session_id"],self.reference,approve=True)
            self.assertEqual(events,["public"])
            with patch.object(wf,"_materialize_patch",side_effect=AssertionError("no new git")):
                reused=wf.share_attempt(b["session_id"],a["session_id"],approve=True)
        self.assertEqual(events,["public"])
        self.assertEqual(reused["new_public_evaluator_calls"],0)
        self.assertEqual(reused["new_git_apply_calls"],0)
        self.assertEqual(reused["new_model_calls"],0)
        self.assertEqual(ran["next"]["prompt_sha256"],reused["next"]["prompt_sha256"])
        c,d=wf.summary(a["session_id"]),wf.summary(b["session_id"])
        self.assertEqual(c["actual_public_evaluator_calls"],1)
        self.assertEqual(d["actual_public_evaluator_calls"],0)
        self.assertEqual(d["verified_public_reuse_hits"],1)
        self.assertEqual(d["tested_git_patches"],1)
        self.assertEqual(c["source_snapshot_sha256"],d["source_snapshot_sha256"])
        a_state=wf._read(a["session_id"])[1]["attempts"][0]
        b_state=wf._read(b["session_id"])[1]["attempts"][0]
        self.assertEqual(a_state["public"],b_state["public"])
        self.assertEqual(a_state["patch_sha256"],b_state["patch_sha256"])

    def test_real_source_reference_pass_reused_and_both_hidden(self):
        a,b=self.make_pair()
        events=[]
        def grader(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"ok","passed":True}
        with patch.object(wf,"grade",side_effect=grader):
            wf.submit(a["session_id"],self.reference,approve=True)
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)
            first=wf.finalize(a["session_id"],approve=True)
            second=wf.finalize(b["session_id"],approve=True)
        self.assertEqual(events,["public","hidden","hidden"])
        self.assertTrue(first["full_success"])
        self.assertTrue(second["full_success"])

    def test_reuse_requires_approval_and_identity(self):
        a,b=self.make_pair()
        with self.assertRaisesRegex(ValueError,"authorization"):
            wf.share_attempt(b["session_id"],a["session_id"])
        with self.assertRaisesRegex(ValueError,"own source"):
            wf.share_attempt(a["session_id"],a["session_id"],approve=True)
        with self.assertRaisesRegex(ValueError,"lacks"):
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)

    def test_missing_or_mutated_source_patch_fails_closed(self):
        a,b=self.make_pair()
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(a["session_id"],self.reference,approve=True)
        path=wf._folder(a["session_id"])/"attempt-1.diff"
        original_patch=path.read_bytes()
        path.write_bytes(original_patch+b"\ninjected\n")
        with self.assertRaisesRegex(ValueError,"checksum"):
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)
        self.assertEqual(wf.summary(b["session_id"])["attempt_count"],0)

    def test_different_test_feedback_configuration_or_task_fails_closed(self):
        a,b=self.make_pair()
        different=wf.start(task_id="youtube-dl-43",policy="adaptive",
                           budget=4,enriched_feedback=False,approve=True)
        other=wf.start(task_id="youtube-dl-27",policy="adaptive",budget=4,approve=True)
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(a["session_id"],self.reference,approve=True)
        for target in (different,other):
            with self.assertRaisesRegex(ValueError,"task, grader or public feedback"):
                wf.share_attempt(target["session_id"],a["session_id"],approve=True)

    def test_prior_candidate_history_mismatch_fails_closed(self):
        a,b=self.make_pair()
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(a["session_id"],self.reference,approve=True)
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)
            wf.submit(a["session_id"],self.reference,approve=True)
        state_path=wf._folder(b["session_id"])/"state.json"
        import json
        altered=json.loads(state_path.read_text())
        altered["attempts"][0]["public"]["status"]="ok"
        wf._atomic(state_path,altered)
        with self.assertRaisesRegex(ValueError,"histories"):
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)

    def test_source_that_was_reused_cannot_be_chained(self):
        a,b=self.make_pair()
        third=wf.start(task_id="youtube-dl-43",policy="adaptive",budget=4,approve=True)
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(a["session_id"],self.reference,approve=True)
            wf.share_attempt(b["session_id"],a["session_id"],approve=True)
        with self.assertRaisesRegex(ValueError,"replayed"):
            wf.share_attempt(third["session_id"],b["session_id"],approve=True)


if __name__=="__main__":
    unittest.main()
