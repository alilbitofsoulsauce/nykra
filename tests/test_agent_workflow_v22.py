"""Real-source workflow integration: auth, durable turns, Git patch, policy, hidden gate."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import agent_workflow as wf
from nykra.v21_grader import function_at, manifest


class RealAgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(wf, "SESSIONS", Path(self.tmp.name) / "sessions")
        p.start()
        self.addCleanup(p.stop)
        self.task = next(x for x in manifest()[0]["tasks"] if x["id"] == "youtube-dl-43")
        self.reference = function_at(self.task, self.task["fixed_commit"])

    def test_approval_required_and_reference_exclusion(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            wf.start(task_id="youtube-dl-43")
        with self.assertRaisesRegex(ValueError, "prevalidation"):
            wf.start(task_id="youtube-dl-25", approve=True)
        with self.assertRaisesRegex(ValueError, "registered"):
            wf.start(task_id="untrusted", approve=True)

    def test_first_next_json_agent_agnostic_and_no_inference(self):
        req = wf.start(task_id="youtube-dl-43", approve=True)
        self.assertTrue(req["agent_required"])
        self.assertFalse(req["model_invocation"])
        self.assertEqual(req["request"], {"kind": "new_root", "parent_attempt_id": None})
        self.assertIn("BUGGY SOURCE:", req["prompt"])
        self.assertEqual(req["remaining_calls"], 4)
        self.assertEqual(req["prompt_sha256"], wf.next_request(req["session_id"])["prompt_sha256"])

    def test_invalid_model_patch_no_git_or_docker(self):
        req = wf.start(task_id="youtube-dl-43", approve=True, budget=1)
        invalid = "def url_basename(url):\n  return ("
        with patch.object(wf, "grade") as grader, patch.object(wf, "_materialize_patch") as patcher:
            r = wf.submit(req["session_id"], invalid, approve=True)
        grader.assert_not_called()
        patcher.assert_not_called()
        self.assertEqual(r["evaluated"]["public"]["status"], "model_invalid_syntax")
        self.assertIsNone(r["evaluated"]["patch_sha256"])
        with patch.object(wf, "grade") as grader:
            result = wf.finalize(req["session_id"], approve=True)
        grader.assert_not_called()
        self.assertFalse(result["full_success"])
        self.assertEqual(result["final_hidden"]["status"], "no_public_repair")

    def test_real_git_patch_then_public_and_hidden_separation(self):
        req = wf.start(task_id="youtube-dl-43", approve=True, budget=2)
        events = []
        def grade(task, *, mode, candidate=None):
            events.append(mode)
            return {"status": "ok", "passed": True}
        with patch.object(wf, "grade", side_effect=grade):
            submitted = wf.submit(req["session_id"], self.reference, approve=True,
                                  tokens=100, model_seconds=2.5, agent_label="relai")
            self.assertEqual(events, ["public"])
            summary = wf.summary(req["session_id"])
            self.assertEqual(summary["tested_git_patches"], 1)
            self.assertTrue(submitted["evaluated"]["actual_git_apply_verified"])
            patch_file = wf._folder(req["session_id"]) / "attempt-1.diff"
            self.assertTrue(patch_file.is_file())
            self.assertEqual(wf._sha(patch_file.read_bytes()), submitted["evaluated"]["patch_sha256"])
            self.assertFalse(submitted["next"]["agent_required"])
            result = wf.finalize(req["session_id"], approve=True)
        self.assertEqual(events, ["public", "hidden"])
        self.assertTrue(result["full_success"])
        self.assertEqual(result["selected_attempt_id"], "attempt-1")
        self.assertEqual(result["model_tokens_reported"], 100)

    def test_only_one_final_hidden_evaluation(self):
        req = wf.start(task_id="youtube-dl-43", approve=True, budget=2)
        with patch.object(wf, "grade", return_value={"status":"test_failed","passed":False}):
            first = wf.submit(req["session_id"], self.reference, approve=True)
            second = wf.submit(req["session_id"], self.reference, approve=True)
        self.assertFalse(second["next"]["agent_required"])
        with patch.object(wf, "grade") as hidden:
            result = wf.finalize(req["session_id"], approve=True)
        hidden.assert_not_called()
        self.assertFalse(result["full_success"])
        with self.assertRaisesRegex(ValueError, "already"):
            wf.finalize(req["session_id"], approve=True)

    def test_actual_adaptive_new_root_after_three_fails(self):
        req = wf.start(task_id="youtube-dl-43", policy="adaptive", approve=True, budget=4)
        with patch.object(wf, "grade", return_value={"status":"test_failed","passed":False}):
            for i in range(3):
                result = wf.submit(req["session_id"], self.reference, approve=True)
        self.assertEqual(result["next"]["request"],
                         {"kind":"new_root","parent_attempt_id":None})
        self.assertIn("Start a new independent solution",result["next"]["prompt"])

    def test_depth_revision_uses_bounded_public_feedback(self):
        req = wf.start(task_id="youtube-dl-43", policy="depth", budget=2, approve=True)
        with patch.object(wf, "grade", return_value={"status":"test_failed","passed":False,
                                                    "diagnostic":"AssertionError: expected filename"}):
            result = wf.submit(req["session_id"], self.reference, approve=True)
        self.assertEqual(result["next"]["request"],
                         {"kind":"revise","parent_attempt_id":"attempt-1"})
        self.assertIn("AssertionError",result["next"]["prompt"])
        self.assertNotIn("_nykra_v21_private_checks",result["next"]["prompt"])

    def test_evaluator_failure_blocks_future_inference(self):
        req = wf.start(task_id="youtube-dl-43", approve=True)
        with patch.object(wf,"grade",return_value={"status":"evaluator_timeout","passed":False}):
            result = wf.submit(req["session_id"],self.reference,approve=True)
        self.assertFalse(result["next"]["agent_required"])
        self.assertEqual(wf.summary(req["session_id"])["status"],"evaluator_blocked")
        with patch.object(wf,"grade") as g:
            final = wf.finalize(req["session_id"],approve=True)
        g.assert_not_called()
        self.assertFalse(final["full_success"])

    def test_session_path_traversal_refused(self):
        with self.assertRaises(ValueError):
            wf.next_request("../secrets")
        with self.assertRaises(ValueError):
            wf.next_request("a" * 32)

    def test_provider_injectable_and_identified(self):
        calls=[]
        def proposer(text,seconds):
            calls.append(text)
            return {"status":"ok","source":self.reference,"tokens":42,"seconds":0.2}
        with patch.object(wf,"grade",return_value={"status":"ok","passed":True}):
            result=wf.run_with_provider(task_id="youtube-dl-43",policy="adaptive",
                                        budget=1,provider=proposer)
        self.assertEqual(len(calls),1)
        self.assertEqual(result["driver"],"codex-inference")
        self.assertEqual(result["model_tokens_reported"],42)
        self.assertTrue(result["full_success"])

    def test_abort_no_hidden_grade(self):
        req=wf.start(task_id="youtube-dl-43",approve=True)
        result=wf.abort(req["session_id"],approve=True)
        self.assertEqual(result["status"],"aborted")
        with self.assertRaises(ValueError):
            wf.submit(req["session_id"],self.reference,approve=True)


if __name__ == "__main__":
    unittest.main()
