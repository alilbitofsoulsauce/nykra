"""Statistically honest v0.19 task accounting and immutable evidence checks."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.v19_report import build_report, save_report


class V19EvidenceTests(unittest.TestCase):
    def test_natural_and_conditional_not_pooled(self):
        r=build_report()
        a=r["natural"]
        b=r["conditional_stalled_history"]
        self.assertEqual(a["registered"],4)
        self.assertEqual(a["shared_public_solves"],3)
        self.assertEqual(a["shared_hidden_verified_posthoc"],3)
        self.assertEqual(a["stats"]["forked_pairs"],1)
        self.assertEqual(a["stats"]["nykra_full_successes"],1)
        self.assertEqual(a["stats"]["baseline_full_successes"],0)
        self.assertEqual(b["stats"]["forked_pairs"],3)
        self.assertEqual(b["stats"]["nykra_full_successes"],3)
        self.assertEqual(b["stats"]["baseline_full_successes"],2)
        self.assertFalse(r["pooled_effect_estimate_valid"])
        self.assertFalse(r["causal_effect_generalized"])

    def test_exact_small_sample_p_values_reported(self):
        r=build_report()
        self.assertEqual(r["natural"]["stats"]["paired_two_sided_exact_sign_p"],1.0)
        self.assertEqual(
            r["conditional_stalled_history"]["stats"]["paired_two_sided_exact_sign_p"],1.0)

    def test_report_prevents_evidence_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"v19_summary.json"
            p.write_text("preserved")
            with patch("nykra.v19_report.EVIDENCE",Path(d)):
                with self.assertRaisesRegex(ValueError,"overwrite"):
                    save_report()
            self.assertEqual(p.read_text(),"preserved")


if __name__=="__main__":
    unittest.main()
