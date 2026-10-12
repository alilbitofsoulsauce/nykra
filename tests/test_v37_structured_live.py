"""Offline integrity checks for real v37 Codex Luna adapter evidence."""
import hashlib
import json
import shutil
import unittest
from pathlib import Path

from nykra.structured_edit_adapter import exact_edits_to_diff
from nykra.v20_grader import REPOS
from nykra.v37_multifile_grader import load_protocol,git_blob

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


class V37EvidenceTests(unittest.TestCase):
    def test_preinference_frozen_buggy_fail_reference_pass(self):
        p=load_protocol()
        rec=read("docs/evidence/v37_multifile_preflight.json")
        self.assertTrue(rec["before_any_v37_codex_model_call"])
        self.assertTrue(rec["eligible"])
        self.assertEqual(rec["protocol_sha256"],
                         hashlib.sha256((ROOT/"docs/evidence/v37_structured_multifile_protocol.json").read_bytes()).hexdigest())
        self.assertEqual({name:x["status"] for name,x in rec["receipts"].items()},
                         {"buggy_public":"test_failed","buggy_hidden":"test_failed",
                          "reference_public":"ok","reference_hidden":"ok"})
        self.assertEqual(p["task"],"youtube-dl-32")
        self.assertEqual(p["arms"],["baseline_raw_git_diff","nykra_structured_adapter"])

    def test_all_twelve_raw_diff_attempts_were_invalid(self):
        d=read("docs/evidence/v37_structured_live/youtube-dl-32_baseline_raw_git_diff.json")
        self.assertEqual(d["provider_calls"],12)
        self.assertEqual(len(d["attempts"]),12)
        self.assertEqual(d["public_docker_calls"],0)
        self.assertEqual(d["hidden_docker_calls"],0)
        self.assertTrue(all(x["public"]["status"]=="invalid_patch" for x in d["attempts"]))
        self.assertGreater(d["reported_usage"]["input_tokens"],300000)
        self.assertEqual(d["status"],"running") # interrupted externally, not solved
        for x in d["attempts"]:
            self.assertEqual(x["patch_sha256"],hashlib.sha256(x["patch"].encode()).hexdigest())

    def test_structured_patch_was_authentic_model_output_and_hidden_verified(self):
        p=load_protocol()
        n=read("docs/evidence/v37_structured_live/youtube-dl-32_nykra_structured_adapter.json")
        self.assertEqual(n["status"],"hidden_verified")
        self.assertEqual(n["provider_calls"],1)
        self.assertEqual(n["public_docker_calls"],1)
        self.assertEqual(n["hidden_docker_calls"],1)
        a=n["attempts"][0]
        self.assertEqual(a["public"]["status"],"ok")
        self.assertEqual(a["hidden"]["status"],"ok")
        self.assertEqual(a["raw_output_sha256"],
                         hashlib.sha256(a["raw_codex_output"].encode()).hexdigest())
        self.assertEqual(a["structured_adapter"]["files_changed"],
                         p["allowed_production_paths"])
        self.assertEqual(a["patch_sha256"],hashlib.sha256(a["patch"].encode()).hexdigest())

    def test_adapter_rebuilds_patch_only_with_pinned_upstream_checkout(self):
        # A public clean clone lacks ignored historical upstream Git sources.
        # Raw receipt integrity above is mandatory; reproduction is optional.
        if shutil.which("git") is None or not (REPOS["youtube-dl"] / ".git").exists():
            self.skipTest("requires Git and separately provisioned historical upstream checkout")
        p=load_protocol()
        n=read("docs/evidence/v37_structured_live/youtube-dl-32_nykra_structured_adapter.json")
        a=n["attempts"][0]
        originals={path:git_blob(p["buggy_commit"],path)
                   for path in p["allowed_production_paths"]}
        derived,receipt=exact_edits_to_diff(
            a["raw_codex_output"],originals=originals,
            allowed_paths=p["allowed_production_paths"])
        self.assertEqual(derived,a["patch"])
        self.assertEqual(receipt["patch_sha256"],a["patch_sha256"])

    def test_real_independent_second_public_and_hidden_docker_receipts(self):
        final=read("docs/evidence/v37_structured_independent_regrade.json")
        self.assertEqual(final["recheck_model_calls"],0)
        self.assertEqual(final["public"]["status"],"ok")
        self.assertEqual(final["hidden"]["status"],"ok")

    def test_summary_does_not_misstate_realized_gain_or_stopped_baseline(self):
        report=read("docs/evidence/v37_structured_summary.json")
        self.assertEqual(report["baseline"]["provider_completed_calls"],12)
        self.assertEqual(report["nykra"]["provider_completed_calls"],1)
        self.assertFalse(report["baseline"]["solved"])
        self.assertTrue(report["baseline"]["not_run_to_completion"])
        self.assertTrue(report["nykra"]["solved"])
        self.assertEqual(report["counterfactual_claim"],"none; baseline interrupted after 12 failed calls")


if __name__=="__main__":
    unittest.main()
