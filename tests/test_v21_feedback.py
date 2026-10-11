"""Fail-closed model-patch validation and public-feedback experiment checks."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from nykra.repair_feedback import validate_replacement,safe_feedback,public_message
from nykra.v21_trial import run_task,validated_protocol

SOURCE="def f(a,b=3):\n return a+b\n"
class V21FeedbackTests(unittest.TestCase):
    def test_syntax_is_model_error_not_evaluator_error(self):
        r=validate_replacement("def f(a,b=3):\n return (",name="f",original=SOURCE)
        self.assertEqual(r["status"],"model_invalid_syntax")
        self.assertIn("SyntaxError",r["diagnostic"])
    def test_signature_and_top_level_contract(self):
        self.assertEqual(validate_replacement("def f(a,b=4):return a",
             name="f",original=SOURCE)["status"],"model_invalid_contract")
        self.assertEqual(validate_replacement("import os\n"+SOURCE,
             name="f",original=SOURCE)["status"],"model_invalid_contract")
        self.assertIsNone(validate_replacement("def f(a,b=3):return a*b",
             name="f",original=SOURCE))
    def test_bounded_sanitized_public_feedback(self):
        raw="C:\\secret\\private\\file.py AssertionError: expected 2 got 3\n"+("x"*4000)+"\x1b[31m"
        s=safe_feedback(raw)
        self.assertLessEqual(len(s),900)
        self.assertNotIn("C:\\secret",s)
        self.assertNotIn("\x1b",s)
        v={"status":"test_failed","passed":False,"diagnostic":"AssertionError: expected 2"}
        self.assertNotIn("AssertionError",public_message(v,enriched=False))
        self.assertIn("AssertionError",public_message(v,enriched=True))
        with self.assertRaises(ValueError):
            public_message({"status":"evaluator_timeout"},enriched=True)
    def test_protocol_registered_eligibility_preserved(self):
        p,sha,pre=validated_protocol()
        self.assertEqual(len(p["tasks"]),6)
        self.assertEqual(sum(x["eligible"] for x in pre["tasks"]),5)
        self.assertTrue(set(x["id"] for x in p["tasks"]).isdisjoint(
            set(p["previously_used_ids"])))
        self.assertEqual(len(sha),64)
    def test_one_equal_revision_per_arm_then_hidden(self):
        p,sha,pre=validated_protocol()
        task=p["tasks"][0]
        prompts=[];events=[]
        def proposer(prompt,seconds):
            prompts.append(prompt);events.append("model")
            return {"status":"ok","source":"def f(a,b=3): return a+b",
                    "tokens":4,"seconds":1}
        def grader(t,*,mode,candidate=None):
            events.append(mode)
            if mode=="hidden":return {"status":"ok","passed":True}
            count=events.count("public")
            return ({"status":"test_failed","passed":False,
                      "diagnostic":"AssertionError: expected 1 but got 0"}
                    if count==1 else {"status":"ok","passed":True})
        with tempfile.TemporaryDirectory() as d:
            with patch("nykra.v21_trial.function_at",return_value=SOURCE),\
                 patch("nykra.v21_trial.grade",side_effect=grader):
                result=run_task(task["id"],Path(d)/"out.json",
                                approve=True,proposer=proposer)
        self.assertEqual(result["status"],"completed")
        self.assertEqual(len(result["arms"]),2)
        self.assertEqual(len(prompts),3)
        self.assertEqual(sum("AssertionError" in x for x in prompts),1)
        last_model=max(i for i,x in enumerate(events) if x=="model")
        first_hidden=min(i for i,x in enumerate(events) if x=="hidden")
        self.assertGreater(first_hidden,last_model)
    def test_approval_and_evidence_overwrite(self):
        p,sha,pre=validated_protocol()
        t=p["tasks"][0]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"existing.json"
            with self.assertRaises(ValueError):
                run_task(t["id"],out)
            out.write_text("keep")
            with self.assertRaises(ValueError):
                run_task(t["id"],out,approve=True)
            self.assertEqual(out.read_text(),"keep")

if __name__=="__main__":unittest.main()
