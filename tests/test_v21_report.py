"""v0.21 evidence aggregation, immutable protocol and honest pair accounting."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from nykra.v21_report import audit,save
from nykra.v21_grader import EVIDENCE

class V21EvidenceTests(unittest.TestCase):
 def test_register_exclusion_and_shared_first_repairs(self):
  d=audit()
  self.assertEqual(d["registered"],6)
  self.assertEqual(d["eligible"],5)
  self.assertEqual(d["reference_exclusions"],["youtube-dl-25"])
  self.assertEqual(d["shared_first_attempt_hidden_verified"],3)
  self.assertEqual(d["valid_paired_tasks"],2)
 def test_enriched_only_one_does_not_prove_general_effect(self):
  d=audit()
  self.assertEqual(d["bare_full_successes"],0)
  self.assertEqual(d["enriched_full_successes"],1)
  self.assertEqual(d["enriched_only"],1)
  self.assertEqual(d["bare_only"],0)
  self.assertEqual(d["paired_exact_two_sided_p"],1.0)
  self.assertTrue(d["not_a_policy_fork_study"])
  self.assertFalse(d["general_effectiveness_improvement_proven"])
 def test_immutable_source_sha_registry(self):
  d=json.loads((EVIDENCE/"manifest.json").read_text())
  ids={x["id"] for x in d["entries"]}
  self.assertIn("v21_machine_summary",ids)
  self.assertIn("v21_protocol_initial",ids)
  self.assertEqual(d["real_external_issue_v21"]["paired_tasks"],2)
 def test_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"v21_summary.json";p.write_text("original")
   with patch("nykra.v21_report.EVIDENCE",Path(d)):
    with self.assertRaisesRegex(ValueError,"overwrite"):
     save()
   self.assertEqual(p.read_text(),"original")
if __name__=="__main__":unittest.main()
