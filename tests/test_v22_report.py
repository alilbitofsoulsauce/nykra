"""Auditable v0.22 integration outcomes and portable source/patch proofs."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import v22_export, v22_report
from nykra.v20_grader import EVIDENCE, ROOT

class V22EvidenceTests(unittest.TestCase):
    def test_two_reused_tasks_and_one_unproductive_real_fork(self):
        r=v22_report.aggregate()
        self.assertEqual(r["registered_reused_upstream_issues"],2)
        self.assertEqual(r["actual_distinct_codex_model_calls"],8)
        self.assertEqual(r["git_applied_source_patches_in_paired_model_trials"],14)
        self.assertEqual(r["policy_divergence_task_count"],1)
        self.assertEqual(r["hidden_verified_successes"],{"depth":1,"adaptive":1})
        self.assertFalse(r["general_effectiveness_improvement_proven"])
        self.assertFalse(r["native_multi_agent_adapters_verified"])

    def test_published_snapshot_is_recomputable(self):
        current=v22_report.aggregate()
        locked=json.loads((EVIDENCE/"v22_workflow_summary.json").read_text())
        self.assertEqual(current,locked)

    def test_reference_cli_transport_not_counted_as_model(self):
        s=json.loads((EVIDENCE/"v22_cli_reference_smoke.json").read_text())
        self.assertEqual(s["candidate_origin"],"UPSTREAM_REFERENCE_CONTROL_NOT_MODEL_GENERATED")
        self.assertTrue(s["complete"])
        self.assertEqual(s["public_status"],"ok")
        self.assertEqual(s["hidden_status"],"ok")

    def test_portable_session_index_sha256s(self):
        p=EVIDENCE/"v22_session_export_index.json"
        index=json.loads(p.read_text())
        self.assertEqual(index["session_count"],5)
        self.assertEqual(index["model_trial_sessions"],4)
        self.assertEqual(index["reference_control_sessions"],1)
        self.assertEqual(sum(len(x["files"]) for x in index["files"]),20)
        for session in index["files"]:
            for file in session["files"]:
                content=(ROOT/file["path"]).read_bytes()
                self.assertEqual(v22_report.sha(ROOT/file["path"]),file["sha256"])
                self.assertEqual(len(content),file["bytes"])

    def test_export_will_not_clobber(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            v22_export.export()

    def test_summary_will_not_clobber(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            v22_report.save()

if __name__=="__main__":
    unittest.main()
