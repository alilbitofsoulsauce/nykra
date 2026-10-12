"""Read-only v0.32 real-provider solve-to-verification evidence checks."""
import hashlib
import json
import unittest
from pathlib import Path

from nykra.model_source_normalizer import normalize_function_imports
from nykra.v20_grader import function_at
from nykra.v21_grader import manifest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/evidence/v32_solved"


class V32RecoveryEvidenceTests(unittest.TestCase):
    def test_real_model_and_rate_limit_are_not_hidden(self):
        history = json.loads((BASE / "youtube-dl-43_baseline_depth.json").read_text())
        self.assertEqual(history["status"], "provider_excluded")
        self.assertEqual(history["provider_error"], "model provider HTTP 429")
        self.assertEqual(len(history["attempts"]), 32)
        self.assertEqual(len({
            a["provider_response_id"] for a in history["attempts"]}), 32)
        self.assertTrue(all(a["reported_provider_cost"] == 0 for a in history["attempts"]))
        self.assertEqual(sum(
            a["provider_tokens"]["total_tokens"] for a in history["attempts"]), 24202)
        self.assertEqual(sum(
            a["provider_tokens"]["total_tokens"]
            for a in history["attempts"][:11]), 6835)
        self.assertEqual(sum(a["public"]["status"] == "model_invalid_contract"
                             for a in history["attempts"]), 29)

    def test_earliest_hidden_verified_is_11_and_only_public_pass_triggers_hidden(self):
        receipt = json.loads(
            (BASE / "youtube-dl-43_chronological_import_replay.json").read_text())
        self.assertEqual(receipt["earliest_hidden_verified_attempt"], "attempt-11")
        self.assertEqual(receipt["public_docker_evaluations"], 4)
        self.assertEqual(receipt["public_reuses"], 4)
        self.assertTrue(receipt["hidden_verified"])
        self.assertEqual(receipt["new_provider_calls"], 0)
        self.assertEqual(len(receipt["raw_outcomes"]), 8)
        checked = [a for a in receipt["raw_outcomes"] if "hidden" in a]
        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0]["attempt_id"], "attempt-11")
        self.assertEqual(checked[0]["public"]["status"], "ok")
        self.assertEqual(checked[0]["hidden"]["status"], "ok")

    def test_imported_function_keeps_model_body_and_reference_signature(self):
        history = json.loads((BASE / "youtube-dl-43_baseline_depth.json").read_text())
        case = next(t for t in manifest()[0]["tasks"] if t["id"] == "youtube-dl-43")
        original = function_at(case, case["buggy_commit"])
        candidate = history["attempts"][10]["source"]
        converted = normalize_function_imports(
            candidate, name=case["function"], original=original)
        self.assertEqual(converted["status"], "normalized_stdlib_imports")
        output_digest = hashlib.sha256(converted["source"].encode()).hexdigest()
        trial = json.loads(
            (BASE / "youtube-dl-43_chronological_import_replay.json").read_text())
        recorded = next(a for a in trial["raw_outcomes"]
                        if a["attempt_id"] == "attempt-11")
        self.assertEqual(output_digest, recorded["normalized_sha256"])
        self.assertEqual(recorded["raw_sha256"], history["attempts"][10]["source_sha256"])

    def test_independent_confirmatory_hidden_pass(self):
        direct = json.loads(
            (BASE / "youtube-dl-43_import_normalization_regrade.json").read_text())
        self.assertEqual(direct["original_v32_attempt_id"], "attempt-29")
        self.assertEqual(direct["import_statements_moved"], 2)
        self.assertEqual(direct["public"]["status"], "ok")
        self.assertEqual(direct["hidden"]["status"], "ok")
        self.assertEqual(direct["new_model_calls_during_regrading"], 0)

    def test_summary_does_not_claim_realized_counterfactual_savings(self):
        data = json.loads((BASE / "v32_recovery_summary.json").read_text())
        self.assertEqual(data["actual_original_successful_model_completions_before_rate_limit"], 32)
        self.assertEqual(data["chronological_first_hidden_verified_attempt"], 11)
        self.assertEqual(data["counterfactual_model_calls_that_would_be_avoided_if_adapter_active_from_start"], 21)
        self.assertEqual(data["counterfactual_provider_reported_tokens_that_would_be_avoided"], 17367)
        self.assertFalse(data["counterfactual_savings_realized_during_original_live_run"])
        self.assertFalse(data["paired_adaptive_vs_baseline_success_uplift_proven"])


if __name__ == "__main__":
    unittest.main()
