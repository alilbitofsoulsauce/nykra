"""v0.24 independent-session cache safety, invalidation and real Git path tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import agent_workflow as wf
from nykra import public_cache_v24 as cache
from nykra.v21_grader import manifest, function_at


class PersistentPublicReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, obj, attr, value in (
            ("sessions", wf, "SESSIONS", self.root/"sessions"),
            ("cache", cache, "CACHE_ROOT", self.root/"cache"),
            ("image", cache, "_image_available", lambda _: True),
        ):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)
        task = next(x for x in manifest()[0]["tasks"] if x["id"]=="youtube-dl-43")
        self.original_reference=function_at(task,task["fixed_commit"])

    def launch(self,*,policy="depth",enriched=True,budget=1):
        return wf.start(task_id="youtube-dl-43", policy=policy, approve=True,
                        budget=budget, enriched_feedback=enriched)

    def test_cold_then_warm_independent_policies_and_feedback(self):
        one=self.launch(policy="depth",enriched=True)
        two=self.launch(policy="adaptive",enriched=False)
        events=[]
        def grader(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"ok","passed":True}
        with patch.object(wf,"grade",side_effect=grader),\
             patch.object(wf,"_materialize_patch",wraps=wf._materialize_patch) as applied:
            a=wf.submit(one["session_id"],self.original_reference,
                        cache_public=True,approve=True)
            b=wf.submit(two["session_id"],self.original_reference,
                        cache_public=True,approve=True)
            self.assertEqual(applied.call_count,1)
            self.assertEqual(events,["public"])
            first=wf.finalize(one["session_id"],approve=True)
            second=wf.finalize(two["session_id"],approve=True)
        self.assertEqual(events,["public","hidden","hidden"])
        self.assertTrue(first["full_success"] and second["full_success"])
        self.assertEqual(first["actual_public_evaluator_calls"],1)
        self.assertEqual(second["actual_public_evaluator_calls"],0)
        self.assertEqual(first["actual_git_apply_calls"],1)
        self.assertEqual(second["actual_git_apply_calls"],0)
        self.assertEqual(second["cross_session_public_cache_hits"],1)
        self.assertEqual(a["evaluated"]["patch_sha256"],b["evaluated"]["patch_sha256"])
        receipts=list((self.root/"cache").glob("*.json"))
        self.assertEqual(len(receipts),1)
        self.assertNotIn('"hidden"',receipts[0].read_text())

    def test_different_model_prompt_history_can_use_same_verified_source(self):
        first=self.launch()
        new=self.launch(policy="adaptive",enriched=False,budget=2)
        syntax_bad="def url_basename(url):\n return ("
        events=[]
        def grader(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"test_failed","passed":False,
                    "diagnostic":"AssertionError: expected video.mp4"}
        with patch.object(wf,"grade",side_effect=grader):
            wf.submit(first["session_id"],self.original_reference,
                      approve=True,cache_public=True)
            wf.submit(new["session_id"],syntax_bad,approve=True,cache_public=True)
            result=wf.submit(new["session_id"],self.original_reference,
                             approve=True,cache_public=True)
        self.assertEqual(events,["public"])
        self.assertTrue(result["evaluated"]["public_cache_hit"])
        self.assertEqual(result["evaluated"]["kind"],"revise")
        self.assertEqual(result["evaluated"]["git_apply_invocations"],0)
        self.assertEqual(result["evaluated"]["public_evaluator_invocations"],0)

    def test_tamper_rejected_and_does_not_run_grader(self):
        req=self.launch()
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(req["session_id"],self.original_reference,approve=True,cache_public=True)
        receipt=next((self.root/"cache").glob("*.json"))
        obj=json.loads(receipt.read_text())
        obj["public"]["status"]="ok"
        receipt.write_text(json.dumps(obj))
        fresh=self.launch()
        with patch.object(wf,"grade") as grader:
            with self.assertRaisesRegex(ValueError,"provenance"):
                wf.submit(fresh["session_id"],self.original_reference,
                          approve=True,cache_public=True)
        grader.assert_not_called()

    def test_different_source_produces_independent_grades(self):
        calls=[]
        def grader(task,*,mode,candidate=None):
            calls.append(candidate)
            return {"status":"test_failed","passed":False}
        alternate=self.original_reference.replace("return", "return", 1).rstrip()+"\n# separate source\n"
        # AST exactly one function with an extra comment is still accepted.
        with patch.object(wf,"grade",side_effect=grader):
            for source in (self.original_reference,alternate):
                req=self.launch()
                wf.submit(req["session_id"],source,approve=True,cache_public=True)
        self.assertEqual(len(calls),2)

    def test_grader_revision_cache_key_invalidation(self):
        a=self.launch()
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}):
            wf.submit(a["session_id"],self.original_reference,approve=True,cache_public=True)
        normal=cache.context
        def different(*args,**kwargs):
            key, payload, recipe=normal(*args,**kwargs)
            payload["evaluator_code_sha256"]["repair_feedback.py"]="0"*64
            return cache._sha(cache._encode(payload)),payload,recipe
        b=self.launch()
        with patch.object(cache,"context",side_effect=different),\
             patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}) as grader:
            r=wf.submit(b["session_id"],self.original_reference,approve=True,cache_public=True)
        self.assertFalse(r["evaluated"]["public_cache_hit"])
        self.assertEqual(grader.call_count,1)

    def test_missing_docker_image_cannot_use_cached_success(self):
        req=self.launch()
        with patch.object(wf,"grade",return_value={"status":"ok","passed":True}):
            wf.submit(req["session_id"],self.original_reference,approve=True,cache_public=True)
        other=self.launch()
        with patch.object(cache,"_image_available",return_value=False),\
             patch.object(wf,"grade") as grader:
            with self.assertRaisesRegex(ValueError,"Docker image"):
                wf.submit(other["session_id"],self.original_reference,
                          cache_public=True,approve=True)
        grader.assert_not_called()

    def test_evaluator_error_not_cached(self):
        with patch.object(wf,"grade",return_value={"status":"evaluator_timeout","passed":False}) as grader:
            a=self.launch()
            wf.submit(a["session_id"],self.original_reference,approve=True,cache_public=True)
            b=self.launch()
            wf.submit(b["session_id"],self.original_reference,approve=True,cache_public=True)
        self.assertEqual(grader.call_count,2)
        self.assertFalse(list((self.root/"cache").glob("*.json")))

    def test_default_does_not_use_cache(self):
        with patch.object(wf,"grade",return_value={"status":"test_failed","passed":False}) as grader:
            for _ in range(2):
                wf.submit(self.launch()["session_id"],self.original_reference,
                          approve=True)
        self.assertEqual(grader.call_count,2)
        self.assertFalse((self.root/"cache").exists())

    def test_model_invalid_syntax_is_never_cached(self):
        bad="def url_basename(url):\n return ("
        with patch.object(wf,"grade") as grader:
            r=wf.submit(self.launch()["session_id"],bad,approve=True,cache_public=True)
        self.assertEqual(r["evaluated"]["public"]["status"],"model_invalid_syntax")
        grader.assert_not_called()
        self.assertFalse((self.root/"cache").exists())

    def test_cache_directory_symlink_protection(self):
        external=self.root/"other"
        external.mkdir()
        root=self.root/"cache"
        try:
            root.symlink_to(external,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaisesRegex(ValueError,"symlink"):
            wf.submit(self.launch()["session_id"],self.original_reference,
                      approve=True,cache_public=True)


if __name__=="__main__":unittest.main()
