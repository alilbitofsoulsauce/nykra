"""v0.23 real-work receipts, reproducibility, strict performance accounting."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

from nykra import v23_report
from nykra.v20_grader import EVIDENCE


class MeasuredAdvantageTests(unittest.TestCase):
    def test_real_run_count_saved_without_model_calls(self):
        r=v23_report.audit()
        self.assertEqual(r["tasks_replayed"],2)
        self.assertEqual(r["actual_new_codex_or_external_model_calls"],0)
        self.assertEqual(r["ordinary_public_docker_calls"],14)
        self.assertEqual(r["nykra_shared_public_docker_calls"],8)
        self.assertEqual(r["public_docker_calls_avoided"],6)
        self.assertEqual(r["actual_git_apply_calls_avoided"],6)
        self.assertEqual(r["public_docker_call_reduction_pct"],42.9)
        self.assertEqual(r["portable_session_count"],8)
        self.assertTrue(r["independent_final_hidden_outcomes_preserved"])
        self.assertFalse(r["general_model_correctness_uplift_proven"])
        self.assertFalse(r["new_model_token_savings_observed"])

    def test_elapsed_reduction_is_measured_not_guaranteed(self):
        r=v23_report.audit()
        self.assertGreater(r["ordinary_total_wall_seconds"],0)
        self.assertGreater(r["nykra_shared_total_wall_seconds"],0)
        self.assertAlmostEqual(
            r["ordinary_total_wall_seconds"]-r["nykra_shared_total_wall_seconds"],
            r["observed_total_wall_seconds_saved"],places=4)
        self.assertGreater(r["observed_wall_reduction_pct"],0)

    def test_snapshot_recomputed_from_real_patches(self):
        self.assertEqual(v23_report.audit(),
                         json.loads((EVIDENCE/"v23_reuse_summary.json").read_text()))

    def test_unmodified_archival_results_and_hidden(self):
        r=v23_report.audit()
        expected={"youtube-dl-27":False,"youtube-dl-43":True}
        for row in r["tasks"]:
            target=expected[row["task_id"]]
            for mode in ("ordinary","shared"):
                self.assertEqual(row["modes"][mode]["full_hidden_outcomes"],
                                 {"depth":target,"adaptive":target})

    def test_independent_cli_reference_control(self):
        r=json.loads((EVIDENCE/"v23_cli_reuse_control.json").read_text())
        self.assertTrue(r["hidden_verified_pass"])
        self.assertEqual(r["new_model_proposals"],0)
        self.assertEqual(r["new_public_docker_calls"],0)
        self.assertEqual(r["new_git_apply_calls"],0)
        self.assertEqual(r["candidate_source"],"v22 prevalidated reference control, not new model")

    def test_immutable_summary_guard(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            v23_report.save()

if __name__=="__main__":
    unittest.main()
