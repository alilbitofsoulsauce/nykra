"""Offline v36 verification of real previously-unused two-file historical task."""
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.transactional_patch import parse_patch
from nykra.v36_multifile_grader import apply_candidate, load_protocol, PROTOCOL_SHA

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


class V36HistoricalMultifileTests(unittest.TestCase):
    def test_frozen_bugsinpy_source_and_independent_docker_preflight(self):
        task=load_protocol()
        self.assertEqual(task["task"],"youtube-dl-35")
        self.assertEqual(task["allowed_production_paths"],[
            "youtube_dl/extractor/arte.py","youtube_dl/utils.py"])
        self.assertTrue(task["created_before_live_v36_model_calls"])
        self.assertEqual(task["hidden_source_sha256"],
                         hashlib.sha256((ROOT/task["hidden_source_path"]).read_bytes()).hexdigest())
        pre=read("docs/evidence/v36_multifile_preflight.json")
        self.assertTrue(pre["eligible"])
        self.assertTrue(pre["graded_before_any_model_proposal"])
        self.assertEqual(pre["protocol_sha256"],PROTOCOL_SHA)
        self.assertEqual({k:r["status"] for k,r in pre["results"].items()},
                         {"buggy_public":"test_failed","buggy_hidden":"test_failed",
                          "reference_public":"ok","reference_hidden":"ok"})
        self.assertIn("20140128",task["public_excerpt"])

    def test_two_independent_codex_arms_both_hidden_verified_but_nykra_slower(self):
        frozen=load_protocol()
        raw=[]
        for arm,number,inputs,outputs in (
            ("baseline_depth",4,64000,2578),
            ("nykra_adaptive",7,203922,6214),
        ):
            with self.subTest(arm=arm):
                state=read("docs/evidence/v36_multifile_live/youtube-dl-35_"+arm+".json")
                self.assertEqual(state["status"],"hidden_verified")
                self.assertEqual(state["provider_calls"],number)
                self.assertEqual(len(state["attempts"]),number)
                self.assertEqual(state["reported_usage"]["input_tokens"],inputs)
                self.assertEqual(state["reported_usage"]["output_tokens"],outputs)
                self.assertEqual(state["public_docker_calls"],1)
                self.assertEqual(state["hidden_docker_calls"],1)
                self.assertEqual(sum(x["public"]["status"]=="invalid_patch"
                                     for x in state["attempts"]),number-1)
                self.assertTrue(all(x["public"]["status"]=="invalid_patch"
                                    for x in state["attempts"][:-1]))
                winning=state["attempts"][-1]
                self.assertEqual(winning["public"]["status"],"ok")
                self.assertEqual(winning["hidden"]["status"],"ok")
                self.assertEqual(state["selected_patch_sha256"],hashlib.sha256(
                    winning["patch"].encode("utf-8")).hexdigest())
                parsed=parse_patch(winning["patch"],frozen["allowed_production_paths"])
                self.assertEqual({x["path"] for x in parsed},
                                 set(frozen["allowed_production_paths"]))
                for trial in state["attempts"]:
                    self.assertEqual(trial["patch_sha256"],
                                     hashlib.sha256(trial["patch"].encode()).hexdigest())
                    self.assertEqual(trial["raw_output_sha256"],
                                     hashlib.sha256(trial["raw_codex_output"].encode()).hexdigest())
                    self.assertIsInstance(trial["model_usage"]["input_tokens"],int)
                    self.assertFalse(trial.get("hidden") and trial["public"]["status"]!="ok")
                if arm=="nykra_adaptive":
                    self.assertEqual(state["attempts"][3]["policy_action"],"new_root")
                else:
                    self.assertEqual(state["attempts"][3]["policy_action"],"revise")
                raw.append(state)
        self.assertEqual(raw[0]["attempts"][0]["prompt_sha256"],
                         raw[1]["attempts"][0]["prompt_sha256"])
        self.assertEqual(len({x["patch_sha256"] for x in [
            raw[0]["attempts"][-1],raw[1]["attempts"][-1]]}),2)

    def test_separate_real_hidden_confirmation_again(self):
        results=read("docs/evidence/v36_multifile_independent_regrade.json")
        self.assertTrue(results["pre_inference_frozen_hidden_suite"])
        self.assertEqual(len(results["samples"]),2)
        for entry in results["samples"]:
            self.assertEqual(entry["public"]["status"],"ok")
            self.assertEqual(entry["hidden"]["status"],"ok")
            self.assertTrue(entry["no_new_model_calls"])
            path=ROOT/"docs/evidence/v36_multifile_live"/(
                "youtube-dl-35_"+entry["arm"]+".json")
            self.assertEqual(entry["raw_trace_sha256"],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_exact_path_patch_allowlist_rejects_new_files_before_git(self):
        frozen=load_protocol()
        example=("diff --git a/unapproved.py b/unapproved.py\n"
                 "new file mode 100644\n--- /dev/null\n+++ b/unapproved.py\n"
                 "@@ -0,0 +1 @@\n+print('oops')\n")
        with patch("nykra.v36_multifile_grader.subprocess.run") as executor:
            receipt=apply_candidate(ROOT,example,frozen["allowed_production_paths"])
        self.assertEqual(receipt["status"],"invalid_patch")
        executor.assert_not_called()

    def test_nonregistered_hidden_source_mutation_is_rejected(self):
        frozen=load_protocol()
        with patch("nykra.v36_multifile_grader.PROTOCOL_SHA","0"*64):
            with self.assertRaisesRegex(ValueError,"protocol SHA"):
                load_protocol()
        self.assertEqual(frozen["model"],"gpt-5.6-luna")


if __name__=="__main__":
    unittest.main()
