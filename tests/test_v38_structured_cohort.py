"""Offline regression checks for v38 multi-issue real Codex + Docker evidence."""
import hashlib
import json
import unittest
from pathlib import Path

from nykra.transactional_patch import parse_patch
from scripts.run_structured_cohort_v38 import prompt

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


class V38StructuredReplicationTests(unittest.TestCase):
    def test_frozen_cohort_and_source_prevalidation(self):
        protocol=read("docs/evidence/v38_cohort_protocol.json")
        self.assertTrue(protocol["frozen_before_model_calls"])
        self.assertEqual(protocol["live_call_limit"],5)
        self.assertEqual({t["id"] for t in protocol["tasks"]},
                         {"youtube-dl-31","youtube-dl-33"})
        pre=read("docs/evidence/v38_preflight.json")
        self.assertTrue(pre["before_first_v38_codex_completion"])
        self.assertEqual(pre["protocol_sha256"],hashlib.sha256(
            (ROOT/"docs/evidence/v38_cohort_protocol.json").read_bytes()).hexdigest())
        for task in protocol["tasks"]:
            self.assertEqual(hashlib.sha256((ROOT/task["hidden_source_path"]).read_bytes()).hexdigest(),
                             task["hidden_sha256"])
            case=pre["tasks"][task["id"]]
            self.assertTrue(case["eligible"])
            self.assertEqual({k:x["status"] for k,x in case["receipts"].items()},
                             {"buggy_public":"test_failed","buggy_hidden":"test_failed",
                              "reference_public":"ok","reference_hidden":"ok"})

    def test_four_model_arms_counts_and_real_source_repair(self):
        proto=read("docs/evidence/v38_cohort_protocol.json")
        counts={"youtube-dl-33":(5,1),"youtube-dl-31":(5,2)}
        for task in proto["tasks"]:
            case=task["id"]
            raw_expected,structured_expected=counts[case]
            raw=read("docs/evidence/v38_structured_live/"+case+"_baseline_raw_git_diff.json")
            structured=read("docs/evidence/v38_structured_live/"+case+"_nykra_structured_adapter.json")
            self.assertEqual(raw["status"],"budget_exhausted")
            self.assertEqual(raw["provider_calls"],raw_expected)
            self.assertEqual(raw["public_docker_calls"],0)
            self.assertEqual(raw["hidden_docker_calls"],0)
            self.assertTrue(all(x["public"]["status"]=="invalid_patch" for x in raw["attempts"]))
            self.assertEqual(structured["status"],"hidden_verified")
            self.assertEqual(structured["provider_calls"],structured_expected)
            self.assertEqual(structured["hidden_docker_calls"],1)
            last=structured["attempts"][-1]
            self.assertEqual(last["public"]["status"],"ok")
            self.assertEqual(last["hidden"]["status"],"ok")
            self.assertEqual(set(last["structured_adapter"]["files_changed"]),
                             set(task["allowed_production_paths"]))
            self.assertEqual({x["path"] for x in parse_patch(
                last["patch"],task["allowed_production_paths"])},
                set(task["allowed_production_paths"]))
            for arm in (raw,structured):
                self.assertEqual(arm["provider_calls"],len(arm["attempts"]))
                self.assertFalse(arm.get("pending_completion"))
                first_prompt=prompt(task,[],{"kind":"new_root","parent_attempt_id":None},arm["arm"])
                self.assertEqual(hashlib.sha256(first_prompt.encode()).hexdigest(),arm["attempts"][0]["prompt_sha256"])
                self.assertNotIn(task["hidden_suite"],first_prompt)
                self.assertNotIn(task["hidden_source_path"],first_prompt)
                for trial in arm["attempts"]:
                    self.assertEqual(trial["patch_sha256"],
                                     hashlib.sha256(trial["patch"].encode()).hexdigest())
                    self.assertEqual(trial["raw_output_sha256"],
                                     hashlib.sha256(trial["raw_codex_output"].encode()).hexdigest())
                    self.assertGreater(trial["model_usage"]["input_tokens"],0)
                    self.assertEqual(len(trial["prompt_sha256"]),64)
        timeline=read("docs/evidence/v38_structured_live/youtube-dl-31_nykra_structured_adapter.json")
        self.assertEqual([x["public"]["status"] for x in timeline["attempts"]],
                         ["test_failed","ok"])

    def test_independent_docker_regression_second_pass(self):
        result=read("docs/evidence/v38_independent_regrade.json")
        self.assertEqual(len(result["records"]),2)
        for item in result["records"]:
            self.assertEqual(item["public"]["status"],"ok")
            self.assertEqual(item["hidden"]["status"],"ok")
            self.assertEqual(item["additional_model_calls"],0)

    def test_aggregate_usage_and_harness_failure_disclosure(self):
        outcome=read("docs/evidence/v38_results.json")
        b=outcome["summary"]["baseline_raw_git_diff"]
        n=outcome["summary"]["nykra_structured_adapter"]
        self.assertEqual((b["calls"],n["calls"]),(10,3))
        self.assertEqual((b["hidden_verified"],n["hidden_verified"]),(0,2))
        self.assertEqual((b["invalid_patch"],n["invalid_patch"]),(10,0))
        self.assertEqual((b["input_tokens"],n["input_tokens"]),(306683,47023))
        self.assertEqual((b["output_tokens"],n["output_tokens"]),(8117,1964))
        self.assertEqual((b["public_docker"],n["public_docker"]),(0,3))
        inc=read("docs/evidence/v38_pretrial_unicode_failure.json")
        self.assertEqual(inc["unreconciled_invocations"],2)
        self.assertTrue(inc["excluded_from_paired_coding_sample"])
        self.assertIn("Baseline arms capped unsolved",outcome["cautions"][1])


if __name__=="__main__":
    unittest.main()
