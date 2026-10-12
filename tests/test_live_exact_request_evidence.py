"""Frozen, read-only checks for real free-model exact-request reuse receipt."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LiveExactReuseEvidenceTests(unittest.TestCase):
    def test_live_provider_receipt_reconciles_without_inference(self):
        data = json.loads(
            (ROOT / "docs/evidence/v30_live_exact_request_reuse.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(data["schema"], "nykra-v30-live-free-exact-request-reuse-v1")
        self.assertEqual(data["request_count"], 3)
        self.assertEqual(data["actual_provider_calls"], 1)
        self.assertEqual(data["provider_calls_avoided"], 2)
        self.assertAlmostEqual(data["call_avoidance_fraction"], 2/3)
        self.assertEqual(data["actual_provider_tokens"], 32)
        self.assertEqual(data["provider_reported_total_cost_usd"], 0)
        self.assertFalse(data["task_correctness_graded"])
        self.assertFalse(data["independent_model_comparison"])
        self.assertEqual(
            sum(int(x["provider_called"]) for x in data["calls"]), 1,
        )
        self.assertEqual(
            sum(x["provider_calls_avoided"] for x in data["calls"]), 2,
        )
        self.assertEqual(
            sum(x["provider_tokens_this_request"] for x in data["calls"]), 32,
        )
        self.assertEqual(len({x["output_sha256"] for x in data["calls"]}), 1)
        self.assertEqual(len({x["original_response_id"] for x in data["calls"]}), 1)
        self.assertFalse(data["calls"][0]["cache_hit"])
        self.assertTrue(all(x["cache_hit"] for x in data["calls"][1:]))
        self.assertFalse(data["raw_prompts_or_model_source_persisted_in_public_evidence"])

    def test_free_request_cli_inference_is_optin_not_a_default(self):
        # Verifies static fixture data, not fresh or future pricing.
        from nykra.free_model_client import FREE_MODEL
        self.assertTrue(FREE_MODEL.fullmatch("cohere/north-mini-code:free"))
        self.assertFalse(FREE_MODEL.fullmatch("cohere/north-mini-code"))
        self.assertFalse(FREE_MODEL.fullmatch("openai/gpt-6"))


if __name__ == "__main__":
    unittest.main()
