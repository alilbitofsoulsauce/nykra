"""Independent cache result audit, external CLI and immutable evidence tests."""
import json
import unittest

from nykra.v20_grader import EVIDENCE
from nykra.v24_report import audit, save


class V24ReportTests(unittest.TestCase):
    def test_genuine_github_git_docker_execution_savings(self):
        a=audit()
        self.assertEqual(a["registered_historical_issues"],2)
        self.assertEqual(a["total_independent_session_runs"],12)
        self.assertEqual(a["total_new_external_model_proposals"],0)
        self.assertEqual(a["ordinary_actual_public_docker_calls"],6)
        self.assertEqual(a["nykra_cached_actual_public_docker_calls"],2)
        self.assertEqual(a["real_public_tests_avoided"],4)
        self.assertEqual(a["nykra_cache_hits"],4)
        self.assertEqual(a["public_docker_reduction_pct"],66.7)
        self.assertEqual(a["actual_git_apply_calls_avoided"],4)

    def test_independent_hidden_outcomes_preserved(self):
        a=audit()
        self.assertTrue(a["historical_patch_outcomes_preserved"])
        self.assertEqual(a["independent_hidden_successes_ordinary"],3)
        self.assertEqual(a["independent_hidden_successes_cached"],3)
        self.assertFalse(a["general_agent_correctness_advantage_proven"])
        self.assertFalse(a["model_token_savings_measured"])

    def test_wall_time_is_observed_not_a_general_promise(self):
        a=audit()
        self.assertGreater(a["observed_seconds_saved"],0)
        self.assertEqual(a["observed_wall_reduction_pct"],53.2)
        self.assertAlmostEqual(a["ordinary_elapsed_seconds"]-a["nykra_cache_elapsed_seconds"],
                               a["observed_seconds_saved"],places=4)

    def test_machine_summary_recomputable(self):
        self.assertEqual(audit(),json.loads((EVIDENCE/"v24_summary.json").read_text()))

    def test_real_process_cli_optin_result(self):
        d=json.loads((EVIDENCE/"v24_cli_independent_control.json").read_text())
        self.assertTrue(d["independent_process_cli"])
        self.assertTrue(d["second_cache_hit"])
        self.assertEqual(d["first_real_public_docker_calls"],1)
        self.assertEqual(d["second_real_public_docker_calls"],0)
        self.assertEqual(d["second_real_git_apply_calls"],0)
        self.assertEqual(d["new_model_calls"],0)

    def test_does_not_overwrite_machine_evidence(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            save()


if __name__=="__main__":
    unittest.main()
