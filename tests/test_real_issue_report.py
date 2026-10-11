"""Pilot evidence must preserve exclusions, null results, and small-sample limits."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nykra.real_issue_report import summarize, save_summary


class RealIssueReportTests(unittest.TestCase):
    def test_all_four_tasks_accounted(self):
        report = summarize(require_complete=True)
        self.assertEqual(report["registered"], 4)
        self.assertEqual(report["paired_complete"], 3)
        self.assertEqual(report["excluded"], 1)
        self.assertEqual(report["task_successes"], {"baseline": 1, "nykra": 1})
        self.assertEqual(report["nykra_only_wins"], 0)
        self.assertEqual(report["baseline_only_wins"], 0)
        self.assertFalse(report["official_swebench"])
        self.assertFalse(report["separate_hidden_verifier"])
        self.assertFalse(report["general_coding_agent_improvement_proven"])
        self.assertFalse(report["causal_uplift_established"])

    def test_no_overwrite_of_existing_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("nykra.real_issue_report.EVIDENCE", Path(folder)):
                with patch("nykra.real_issue_report.summarize", return_value={"check": True}):
                    result = save_summary()
                    self.assertEqual(json.loads(result.read_text()), {"check": True})
                    with self.assertRaisesRegex(ValueError, "overwrite"):
                        save_summary()


if __name__ == "__main__":
    unittest.main()
