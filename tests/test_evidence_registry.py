"""Keep public README evidence numerators and immutable artifacts in sync."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EvidenceRegistryTests(unittest.TestCase):
    def test_manifest_integrity(self):
        manifest = json.loads((ROOT / "docs/evidence/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "nykra-public-evidence-manifest-v1")
        for record in manifest["entries"]:
            path = ROOT / record["path"]
            with self.subTest(path=record["path"]):
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_public_claims_match_saved_raw_outcomes(self):
        grid = json.loads((ROOT / "docs/evidence/grid_paired_seed20261011.json").read_text())
        study = json.loads((ROOT / "docs/evidence/v13_coding_study_results.json").read_text())
        raw_candidates = (ROOT / "docs/evidence/v13_model_authored_first_attempts.json").read_bytes()
        self.assertEqual(grid["sample"], 48)
        self.assertEqual(grid["results"]["baseline_successes"], 19)
        self.assertEqual(grid["results"]["challenger_successes"], 48)
        self.assertFalse(grid["limits"]["general_agent_improvement_proven"])
        self.assertEqual(study["first_attempt_tasks_passed"], 8)
        self.assertEqual(study["heldout_test_cases_passed"], 320)
        self.assertEqual(study["heldout_test_cases"], 320)
        self.assertFalse(study["study_limits"]["real_model_gain_proven"])
        self.assertEqual(hashlib.sha256(raw_candidates).hexdigest(),
                         study["candidate_manifest_sha256"])

    def test_native_codex_scores_match_raw_candidates_and_protocol(self):
        from nykra.native_codex_pilot import score_source
        root = ROOT / "docs/evidence"
        first = json.loads((root / "v14_native_codex_v1_summary.json").read_text())
        second = json.loads((root / "v14_native_codex_v2_summary.json").read_text())
        self.assertEqual(first["baseline_successes"], 1)
        self.assertEqual(first["nykra_successes"], 1)
        self.assertEqual(second["arms"]["baseline"]["task_solved"], 1)
        self.assertEqual(second["arms"]["nykra"]["task_solved"], 1)
        self.assertEqual(second["arms"]["baseline"]["hidden_cases_passed"], 32)
        self.assertEqual(second["arms"]["nykra"]["hidden_cases_passed"], 37)
        protocol = (root / "v14_codex_pilot_protocol_v2.json").read_bytes()
        protocol_hash = hashlib.sha256(protocol).hexdigest()
        for task in ("reservation-gaps", "ledger-undo", "csv-records", "normalized-path"):
            with self.subTest(task=task):
                raw = json.loads((root / ("v14_codex_v2_" + task + ".json")).read_text())
                self.assertEqual(raw["status"], "completed")
                self.assertEqual(raw["protocol_sha256"], protocol_hash)
                self.assertEqual({arm["arm"] for arm in raw["arms"]}, {"baseline", "nykra"})
                for arm in raw["arms"]:
                    self.assertLessEqual(arm["attempts_used"], 2)
                    self.assertEqual(arm["final_heldout_total"], 32)
                    valid = [a for a in arm["attempts"]
                             if a["status"] == "ok" and a.get("source")]
                    selected = max(valid, key=lambda a: (a["training"]["score"], -a["attempt_number"])) if valid else None
                    expected = score_source(task, selected["source"], heldout=True)["passed"] if selected else 0
                    self.assertEqual(expected, arm["final_heldout_passed"])
                    self.assertEqual(expected == 32, arm["final_heldout_success"])

    def test_v15_repository_patch_scores_and_source_integrity(self):
        import tempfile
        from nykra.repository_repair_trial import (
            grade, prepare_repository, replace_function, protocol
        )
        root = ROOT / "docs/evidence"
        raw_protocol = (root / "v15_repo_pilot_protocol.json").read_bytes()
        prot = protocol()
        doc = json.loads((root / "v15_repo_repair_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["protocol_sha256"], hashlib.sha256(raw_protocol).hexdigest())
        self.assertEqual(doc["task_count"], 6)
        self.assertEqual(doc["arm_results"]["baseline"]["solved"], 6)
        self.assertEqual(doc["arm_results"]["nykra"]["solved"], 6)
        self.assertFalse(doc["causal_improvement_proven"])
        self.assertEqual(doc["nykra_revision_turns_executed"], 0)
        for task in prot["tasks"]:
            with self.subTest(task=task["id"]):
                stored = json.loads((root / ("v15_" + task["id"] + ".json")).read_text(encoding="utf-8"))
                self.assertEqual(stored["state"], "completed")
                self.assertEqual(stored["protocol_sha256"], doc["protocol_sha256"])
                self.assertEqual([x["arm"] for x in stored["arms"]], task["order"])
                with tempfile.TemporaryDirectory(prefix="nykra-v15-integrity-") as directory:
                    checkout = prepare_repository(task, Path(directory))
                    target = checkout / task["file"]
                    baseline = target.read_text(encoding="utf-8")
                    for arm in stored["arms"]:
                        self.assertEqual(arm["attempts_used"], 1)
                        self.assertEqual(arm["hidden_total"], 26)
                        chosen = next(x for x in arm["attempts"]
                                      if x["attempt"] == arm["selected_attempt"])
                        self.assertEqual(
                            hashlib.sha256(chosen["source"].encode("utf-8")).hexdigest(),
                            chosen["source_sha256"]
                        )
                        try:
                            changed = replace_function(baseline, task["function"], chosen["source"])
                            target.write_text(changed, encoding="utf-8")
                            independent = grade(checkout, task, heldout=True)
                            self.assertEqual(independent["passed"], arm["hidden_passed"])
                            self.assertEqual(independent["total"], 26)
                            self.assertEqual(independent["score"] == 1., arm["fully_solved"])
                        finally:
                            target.write_text(baseline, encoding="utf-8")

    def test_v16_shared_policy_model_smoke_recomputes_heldout(self):
        import tempfile
        from nykra.repository_repair_trial import (
            grade, prepare_repository, replace_function, protocol
        )
        src = ROOT / "docs/evidence/v16_real_codex_policy_smoke.json"
        result = json.loads(src.read_text(encoding="utf-8"))
        self.assertEqual(result["policy"], "adaptive")
        self.assertEqual(result["protocol_id"], "nykra-v16-trusted-source-policy-smoke-v1")
        self.assertFalse(result["comparative_evidence"])
        self.assertFalse(result["general_coding_agent_improvement_proven"])
        self.assertEqual(result["evaluations_used"], 1)
        self.assertEqual(result["heldout_passed"], 26)
        self.assertEqual(result["heldout_total"], 26)
        self.assertEqual(result["candidate_attempts"][0]["kind"], "new_root")
        first = result["candidate_attempts"][0]
        self.assertEqual(
            hashlib.sha256(first["source"].encode("utf-8")).hexdigest(),
            first["source_sha256"],
        )
        task = next(x for x in protocol()["tasks"] if x["id"] == result["task_id"])
        with tempfile.TemporaryDirectory(prefix="nykra-v16-evidence-") as directory:
            checkout = prepare_repository(task, Path(directory))
            filename = checkout / task["file"]
            original = filename.read_text(encoding="utf-8")
            filename.write_text(
                replace_function(original, task["function"], first["source"]),
                encoding="utf-8"
            )
            independent = grade(checkout, task, heldout=True)
            self.assertEqual(independent["passed"], result["heldout_passed"])
            self.assertEqual(independent["total"], result["heldout_total"])

    def test_readme_links_to_evidence_and_disclaims_general_gain(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for required in (
            "docs/EVIDENCE.md",
            "docs/BENCHMARK_RESULTS.md",
            "docs/evidence/grid_paired_seed20261011.json",
            "docs/REAL_CODING_STUDY.md",
            "docs/evidence/v13_coding_study_results.json",
            "docs/evidence/v13_model_authored_first_attempts.json",
            "docs/evidence/native_runner_probes_2026-10-11.json",
            "docs/NATIVE_CODEX_PILOT.md",
            "docs/evidence/v14_native_codex_v1_summary.json",
            "docs/evidence/v14_native_codex_v2_summary.json",
            "docs/REPOSITORY_REPAIR_PILOT.md",
            "docs/evidence/v15_repo_pilot_protocol.json",
            "docs/evidence/v15_repo_repair_summary.json",
            "docs/EXTERNAL_EVALUATION.md",
            "docs/evidence/v16_real_codex_policy_smoke.json",
            "26/26",
            "156/156",
            "6/6",
            "37/128",
            "32/128",
            "zero measurable uplift",
            "general coding-agent effectiveness",
        ):
            with self.subTest(claim=required):
                self.assertIn(required, readme)


if __name__ == "__main__":
    unittest.main()
