"""Evidence-wide checks for v0.20 previously unseen upstream issue replication."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.v20_report import audit,save


class V20ReportTests(unittest.TestCase):
    def test_all_registered_issues_and_two_forks(self):
        r=audit()
        self.assertEqual(r["registered"],4)
        self.assertEqual(r["prevalidated_eligible"],4)
        self.assertEqual(r["genuine_forked_tasks"],2)
        self.assertEqual(r["invalid_prefixes"],1)
        self.assertEqual(r["shared_prefix_public_solutions"],1)
        self.assertEqual(r["shared_prefix_posthoc_hidden_successes"],1)

    def test_zero_replication_result_does_not_count_draws_as_tasks(self):
        r=audit()
        for arm in ("baseline","nykra"):
            v=r["observed_by_policy"][arm]
            self.assertEqual(v["task_successes"],0)
            self.assertEqual(v["sample_successes"],0)
            self.assertEqual(v["sample_calls"],4)
        self.assertFalse(r["general_causal_improvement_proven"])
        self.assertTrue(r["not_independent_samples"])
        self.assertFalse(r["official_swebench"])

    def test_refuses_to_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"v20_summary.json"
            path.write_text("original")
            with patch("nykra.v20_report.EVIDENCE",Path(tmp)):
                with self.assertRaisesRegex(ValueError,"overwrite"):
                    save()
            self.assertEqual(path.read_text(),"original")


if __name__=="__main__":
    unittest.main()
