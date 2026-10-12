"""Offline integrity checks for v39–v40 real cross-repo and second-model receipts."""
import hashlib
import json
import unittest
from pathlib import Path

from nykra.structured_edit_adapter import exact_edits_to_diff
from nykra.v40_terra_grader import git_blob
from scripts.run_terra_policy_v40 import prompt

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


class CrossRepoModelEvidenceTests(unittest.TestCase):
    def test_crossrepo_preinference_sha_frozen_and_reference_eligible(self):
        proto=read("docs/evidence/v39_pysnooper_protocol.json")
        self.assertEqual(proto["project"],"PySnooper")
        self.assertEqual(len(proto["allowed_production_paths"]),2)
        for phase in ("public","hidden"):
            self.assertEqual(hashlib.sha256(
                (ROOT/proto[phase+"_source_path"]).read_bytes()).hexdigest(),
                proto[phase+"_source_sha256"])
        rejected=read("docs/evidence/v39_pysnooper_preflight.json")
        self.assertFalse(rejected["eligible"])
        self.assertEqual(rejected["receipts"]["reference_public"]["status"],"setup_error")
        valid=read("docs/evidence/v39_pysnooper_preflight_validated.json")
        self.assertTrue(valid["eligible"])
        self.assertTrue(valid["before_any_v39_model_completion"])
        self.assertEqual({k:x["status"] for k,x in valid["receipts"].items()},
                         {"buggy_public":"test_failed","buggy_hidden":"test_failed",
                          "reference_public":"ok","reference_hidden":"ok"})

    def test_luna_cross_repo_0_of_2_hidden_verified_and_nonapplicable_baseline(self):
        baseline=read("docs/evidence/v39_pysnooper_live/PySnooper-1_baseline_raw_git_diff.json")
        structured=read("docs/evidence/v39_pysnooper_live/PySnooper-1_nykra_structured_adapter.json")
        for data in (baseline,structured):
            self.assertEqual(data["status"],"budget_exhausted")
            self.assertEqual(data["provider_calls"],5)
            self.assertEqual(len(data["attempts"]),5)
        self.assertTrue(all(a["public"]["status"]=="invalid_patch" for a in baseline["attempts"]))
        self.assertEqual(baseline["public_docker_calls"],0)
        self.assertEqual(structured["public_docker_calls"],5)
        self.assertEqual(structured["hidden_docker_calls"],5)
        self.assertTrue(all(a["public"]["status"]=="ok" and a["hidden"]["status"]=="test_failed"
                            for a in structured["attempts"]))
        self.assertEqual(baseline["reported_usage"]["input_tokens"],192223)
        self.assertEqual(structured["reported_usage"]["input_tokens"],126494)

    def test_external_provider_blocked_but_other_codex_model_replied(self):
        external=read("docs/evidence/v39_opencode_provider_probe.json")
        self.assertFalse(external["verified_model_completion"])
        self.assertFalse(external["verified_coding_completion"])
        terra=read("docs/evidence/v39_second_codex_model_probe.json")
        self.assertEqual(terra["outcome"],"verified_reply")
        self.assertEqual(terra["model"],"gpt-5.6-terra")
        self.assertEqual(terra["message"],"READY")
        self.assertFalse(terra["is_distinct_provider"])
        self.assertGreater(terra["reported_usage"]["input_tokens"],0)

    def test_posthoc_terra_frozen_again_and_two_policy_arms_identical_initial_prompt(self):
        p=read("docs/evidence/v40_terra_policy_protocol.json")
        pre=read("docs/evidence/v40_terra_preflight.json")
        self.assertTrue(pre["eligible"])
        self.assertEqual({key:x["status"] for key,x in pre["receipts"].items()},
                         {"buggy_public":"test_failed","buggy_hidden":"test_failed",
                          "reference_public":"ok","reference_hidden":"ok"})
        for phase in ("public","hidden"):
            self.assertEqual(hashlib.sha256(
                (ROOT/p[phase+"_source_path"]).read_bytes()).hexdigest(),
                p[phase+"_source_sha256"])
        task={**p,"public_excerpt":(ROOT/p["public_source_path"]).read_text(encoding="utf-8")}
        initial=prompt(task,[],{"kind":"new_root","parent_attempt_id":None},"structured_depth")
        adaptive=prompt(task,[],{"kind":"new_root","parent_attempt_id":None},"structured_adaptive")
        self.assertEqual(initial,adaptive)
        self.assertNotIn(p["hidden_suite"],initial)
        self.assertNotIn(p["hidden_source_path"],initial)
        self.assertEqual(p["hidden_gate"][:10],"Grade hidd")

    def test_two_independent_terra_patches_both_real_public_hidden_pass(self):
        proto=read("docs/evidence/v40_terra_policy_protocol.json")
        p={}
        for arm in ("structured_depth","structured_adaptive"):
            trial_path="docs/evidence/v40_terra_policy_live/PySnooper-1_"+arm+".json"
            d=read(trial_path)
            self.assertEqual(d["status"],"hidden_verified")
            self.assertEqual(d["provider_calls"],1)
            self.assertEqual(d["public_docker_calls"],1)
            self.assertEqual(d["hidden_docker_calls"],1)
            a=d["attempts"][0]
            self.assertEqual(a["policy_action"],"new_root")
            self.assertEqual(a["public"]["status"],"ok")
            self.assertEqual(a["hidden"]["status"],"ok")
            original={name:git_blob(proto["buggy_commit"],name,"PySnooper-1")
                      for name in proto["allowed_production_paths"]}
            patch,receipt=exact_edits_to_diff(a["raw_codex_output"],originals=original,
                  allowed_paths=proto["allowed_production_paths"])
            self.assertEqual(patch,a["patch"])
            self.assertEqual(receipt["files_changed"],proto["allowed_production_paths"])
            self.assertEqual(hashlib.sha256(patch.encode()).hexdigest(),a["patch_sha256"])
            p[arm]=a["prompt_sha256"]
        self.assertEqual(p["structured_depth"],p["structured_adaptive"])
        regrade=read("docs/evidence/v40_independent_regrade.json")
        self.assertEqual(len(regrade["records"]),2)
        for record in regrade["records"]:
            self.assertEqual(record["public"]["status"],"ok")
            self.assertEqual(record["hidden"]["status"],"ok")
            self.assertEqual(record["extra_provider_calls"],0)


if __name__=="__main__":
    unittest.main()
