"""v0.20 independent sampling, hidden confidentiality, provenance and safety."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.v20_grader import manifest, _commands, grade
from nykra.v20_trial import validated_protocol, run_task


class V20Tests(unittest.TestCase):
    def setUp(self):
        self.protocol,self.digest,self.preflight=validated_protocol()
        self.task=self.protocol["tasks"][0]

    def test_frozen_unused_cross_project_population_and_preflight(self):
        ids=[x["id"] for x in self.protocol["tasks"]]
        self.assertEqual(len(ids),4)
        self.assertEqual({x["project"] for x in self.protocol["tasks"]},{"youtube-dl","tqdm"})
        self.assertTrue(set(ids).isdisjoint(self.protocol["previously_used_task_ids"]))
        self.assertEqual(ids,[x["id"] for x in self.preflight["tasks"]])
        self.assertTrue(all(x["eligible"] for x in self.preflight["tasks"]))
        self.assertEqual(self.protocol["fork_draws_per_arm"],2)
        self.assertEqual(self.protocol["shared_prefix_calls"],3)

    def test_hidden_public_selectors_are_disjoint(self):
        for t in self.protocol["tasks"]:
            public=str(_commands(t,"public"))
            hidden=str(_commands(t,"hidden"))
            self.assertNotIn(t["public_test"],hidden)
            self.assertNotIn("_nykra_v20_private_checks",public)

    def test_oversize_patch_rejected_before_docker(self):
        with patch("nykra.v20_grader.subprocess.run") as process:
            r=grade(self.task,mode="public",candidate="x"*10001)
        self.assertEqual(r["status"],"invalid_patch")
        process.assert_not_called()

    def test_refuses_missing_approval_and_evidence_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"sample.json"
            with self.assertRaises(ValueError):
                run_task(self.task["id"],out)
            out.write_text("preserve")
            with self.assertRaises(ValueError):
                run_task(self.task["id"],out,approve=True)
            self.assertEqual(out.read_text(),"preserve")

    def test_real_policy_fork_and_two_identical_prompt_draws_each_arm(self):
        events=[]
        def propose(prompt,seconds):
            events.append(("model",prompt))
            # All 3 common attempts fail. Distinct policy post-fork results.
            if "EXPLORATION ACTION:" in prompt:
                is_root="Start an independent new root" in prompt
                return {"status":"ok","source":"root_pass" if is_root else "revise_fail",
                        "tokens":100,"seconds":1}
            return {"status":"ok","source":"shared_fail","tokens":100,"seconds":1}
        def evaluator(task,*,mode,candidate=None):
            events.append(("grade",mode,candidate))
            passing=candidate=="root_pass"
            return {"status":"ok" if passing else "test_failed","passed":passing}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"result.json"
            with patch("nykra.v20_trial.function_at",return_value="def unescapeHTML(s):return s"), \
                 patch("nykra.v20_trial.grade",side_effect=evaluator):
                r=run_task(self.task["id"],out,approve=True,proposer=propose)
        self.assertEqual(r["status"],"completed")
        self.assertEqual(len(r["shared_prefix"]),3)
        self.assertEqual(len(r["draws"]),4)
        self.assertEqual(r["fork_actions"]["baseline"]["kind"],"revise")
        self.assertEqual(r["fork_actions"]["nykra"]["kind"],"new_root")
        self.assertEqual(len([x for x in events if x[0]=="model"]),7)
        self.assertEqual(len([x for x in events if x[:2]==("grade","hidden")]),2)
        # Every hidden grade after all model calls; none used as feedback.
        final_model=max(i for i,v in enumerate(events) if v[0]=="model")
        first_hidden=min(i for i,v in enumerate(events) if v[:2]==("grade","hidden"))
        self.assertGreater(first_hidden,final_model)
        for arm in ("baseline","nykra"):
            prompts=[v[1] for v in events if v[0]=="model"
                     and "EXPLORATION ACTION:" in v[1]
                     and (("new root" in v[1])==(arm=="nykra"))]
            self.assertEqual(len(prompts),2)
            self.assertEqual(prompts[0],prompts[1])
        self.assertEqual(sum(x["full_success"] for x in r["draws"] if x["arm"]=="nykra"),2)
        self.assertEqual(sum(x["full_success"] for x in r["draws"] if x["arm"]=="baseline"),0)

    def test_prefix_success_is_not_assigned_to_policy(self):
        def propose(prompt,seconds):
            return {"status":"ok","source":"shared_good","tokens":5,"seconds":1}
        with tempfile.TemporaryDirectory() as d:
            with patch("nykra.v20_trial.function_at",return_value="def unescapeHTML(s):return s"),\
                 patch("nykra.v20_trial.grade",return_value={"status":"ok","passed":True}):
                r=run_task(self.task["id"],Path(d)/"r.json",approve=True,proposer=propose)
        self.assertEqual(r["status"],"not_forkable")
        self.assertEqual(r["shared_prefix_reason"],"public_solved")
        self.assertEqual(len(r["shared_prefix"]),1)
        self.assertFalse(r["draws"])


if __name__=="__main__":
    unittest.main()
