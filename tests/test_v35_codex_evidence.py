"""Offline forensic verification of real Codex Luna and Docker receipts."""
import hashlib,json,unittest
from pathlib import Path
from nykra.v20_grader import manifest

ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads((ROOT/path).read_text(encoding="utf-8"))

class CodexLunaEvidenceTests(unittest.TestCase):
    def test_three_matched_real_upstream_tasks_and_independent_hidden_passes(self):
        aggregated=read("docs/evidence/v35_codex_luna_results.json")
        self.assertFalse(aggregated["matched_adaptive_accuracy_uplift_observed"])
        self.assertFalse(aggregated["matched_model_call_saving_observed"])
        self.assertEqual(aggregated["matched_summary"]["baseline_depth"]["hidden_verified_solved"],3)
        self.assertEqual(aggregated["matched_summary"]["nykra_adaptive"]["hidden_verified_solved"],3)
        self.assertEqual(aggregated["matched_summary"]["baseline_depth"]["calls"],3)
        self.assertEqual(aggregated["matched_summary"]["nykra_adaptive"]["calls"],3)
        seen=set()
        for issue in aggregated["matched_real_historical_tasks"]:
            for arm in ("baseline_depth","nykra_adaptive"):
                info=aggregated["matched_study_results"][issue+"_"+arm]
                raw=(ROOT/info["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),info["sha256"])
                state=json.loads(raw)
                self.assertEqual(state["status"],"solved")
                self.assertEqual(state["codex_completions"],1)
                self.assertEqual(state["hidden_runs"],1)
                chosen=state["attempts"][-1]
                self.assertEqual(chosen["public"]["status"],"ok")
                self.assertEqual(chosen["hidden_receipt"]["status"],"ok")
                self.assertEqual(chosen["policy_action"],
                                 "new_root" if arm=="nykra_adaptive" else "revise")
                self.assertEqual(chosen["source_sha256"],
                                 hashlib.sha256(chosen["source"].encode()).hexdigest())
                self.assertEqual(chosen["raw_sha256"],
                                 hashlib.sha256(chosen["raw_codex_output"].encode()).hexdigest())
                self.assertFalse(chosen["codex_receipt"]["tool_activity"])
                self.assertGreater(state["codex_reported_usage"]["input_tokens"],0)
                self.assertGreater(state["codex_reported_usage"]["output_tokens"],0)

    def test_actual_ten_luna_failures_and_feedback_rescue_hidden_verified(self):
        final=read("docs/evidence/v35_codex_luna_results.json")
        history=read(final["hard_stall"]["file"])
        self.assertEqual(history["codex_completions"],10)
        self.assertTrue(all(a["public"]["status"]=="test_failed"
                            for a in history["attempts"] if not a["inherited"]))
        pilot=read(final["hard_task_rescue"]["source_file"])
        self.assertEqual(pilot["status"],"solved")
        self.assertEqual(pilot["new_codex_calls"],2)
        self.assertEqual(pilot["new_public_docker_grades"],2)
        self.assertEqual(pilot["new_hidden_docker_grades"],1)
        self.assertEqual(pilot["attempts"][0]["public"]["status"],"test_failed")
        winning=pilot["attempts"][-1]
        self.assertEqual(winning["public"]["status"],"ok")
        self.assertEqual(winning["hidden"]["status"],"ok")
        self.assertEqual(winning["source_sha256"],
                         "43dae3bfa836c64e438c4da310d58cd7c45d7fab27f5d9fa067fb144a6890182")
        retest=read("docs/evidence/v35_rescue/youtube-dl-5_independent_recheck.json")
        self.assertTrue(retest["pass"])
        self.assertEqual(retest["standalone_official_v20_public"]["status"],"ok")
        self.assertEqual(retest["standalone_official_v20_hidden"]["status"],"ok")
        self.assertEqual(pilot["new_codex_calls"]+history["codex_completions"],12)
        self.assertFalse(final["hard_task_rescue"]["causal_adaptive_policy_uplift_proven"])

    def test_protocols_and_debug_receipt_are_frozen_and_public_only(self):
        data=read("docs/evidence/v35_codex_luna_results.json")
        for key in ("v33","v34","v35"):
            path={"v33":"docs/evidence/v33_codex_luna_protocol.json",
                  "v34":"docs/evidence/v34_codex_hard_forks_protocol.json",
                  "v35":"docs/evidence/v35_feedback_rescue_protocol.json"}[key]
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
                             data["protocols"][key])
        debug=read("docs/evidence/v34_codex_hard_forks/youtube-dl-5_public_diagnostic.json")
        self.assertEqual(debug["mode"],"public only")
        self.assertEqual(debug["result"]["status"],"test_failed")
        self.assertIn("AssertionError",debug["result"]["diagnostic"])
        self.assertLessEqual(len(debug["result"]["diagnostic"]),900)
        self.assertEqual(debug["live_provider_calls_prior"],10)

if __name__=="__main__":
    unittest.main()
