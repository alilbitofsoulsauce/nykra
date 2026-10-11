"""Follow-up V2 guarantees equal validation feedback and clean evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.native_codex_pilot_v2 import (
    PROTOCOL_PATH, describe_validation, evaluate_arm, execute_task,
    invoke, make_prompt,
)


class NativePilotV2Tests(unittest.TestCase):
    def test_fixed_protocol_is_followup_not_a_replacement(self):
        doc = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(doc["protocol_id"], "nykra-native-codex-matched-pilot-v2")
        self.assertEqual(doc["attempt_limit_per_task_arm"], 2)
        self.assertEqual(len(doc["task_order"]), 4)
        self.assertEqual(sum(x["run_order"][0] == "nykra" for x in doc["task_order"]), 2)

    def test_ast_errors_deterministic_and_safe_to_share(self):
        source = "def solve(text):\n    return text.split(',')\n"
        message = describe_validation(source)
        self.assertIn("ValueError:", message)
        self.assertIn("only restricted built-in calls", message)
        self.assertIsNone(describe_validation("def solve(x):\n    return x\n"))

    def test_both_arms_share_first_prompt_and_public_failures(self):
        first = make_prompt("csv-records", arm="baseline", previous=None)
        same = make_prompt("csv-records", arm="nykra", previous=None)
        self.assertEqual(first, same)
        parent = {
            "source": "def solve(x):\n    return x.split(',')\n",
            "validation_error": "ValueError: only restricted built-in calls are allowed",
            "training": {
                "status": "invalid_source", "passed": 0, "total": 14,
                "failure_examples": [],
            },
        }
        baseline = make_prompt("csv-records", arm="baseline", previous=parent)
        guided = make_prompt("csv-records", arm="nykra", previous=parent)
        for value in (parent["source"], parent["validation_error"], '"passed": 0'):
            self.assertIn(value, baseline)
            self.assertIn(value, guided)
        self.assertIn("BASELINE POLICY", baseline)
        self.assertIn("NYKRA POLICY", guided)

    def test_invalid_first_source_is_retained_for_second_attempt_both_arms(self):
        bad = {
            "status": "invalid_source",
            "source": "def solve(base, relative):\n    return base.split('/')\n",
            "elapsed_seconds": 0.1, "tokens_reported": 15,
            "validation_error": "ValueError: only restricted built-in calls are allowed",
        }
        second = dict(bad, elapsed_seconds=0.12)
        for arm in ("baseline", "nykra"):
            with self.subTest(arm=arm), patch(
                "nykra.native_codex_pilot_v2.invoke", side_effect=[bad, second],
            ) as model:
                out = evaluate_arm("normalized-path", arm, executable=Path("none"), timeout=3)
            self.assertEqual(model.call_count, 2)
            self.assertEqual(out["attempts_used"], 2)
            self.assertEqual(out["final_heldout_passed"], 0)
            self.assertIn(bad["validation_error"], model.call_args.args[0])
            if arm == "nykra":
                self.assertEqual(out["attempts"][1]["parent_attempt"], 1)
            else:
                self.assertIsNone(out["attempts"][1]["parent_attempt"])

    def test_failure_remains_failure_if_model_never_returns_source(self):
        no_answer = {
            "status": "model_timeout", "source": None,
            "elapsed_seconds": 1.0, "tokens_reported": None,
            "validation_error": None,
        }
        with patch("nykra.native_codex_pilot_v2.invoke", return_value=no_answer):
            result = evaluate_arm("csv-records", "nykra",
                                  executable=Path("none"), timeout=2)
        self.assertEqual(result["attempts_used"], 2)
        self.assertFalse(result["final_heldout_success"])
        self.assertFalse(result["token_reporting_complete"])

    def test_approval_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "v2.json"
            with self.assertRaises(ValueError):
                execute_task("csv-records", path, approval=False)
            path.write_text("original", encoding="utf-8")
            with self.assertRaises(ValueError):
                execute_task("csv-records", path, approval=True)
            self.assertEqual(path.read_text(), "original")

    def test_missing_runner_fails_closed(self):
        with tempfile.TemporaryDirectory() as home:
            result = invoke("test", executable=Path(home)/"missing.exe", timeout=2)
        self.assertEqual(result["status"], "model_binary_missing")
        self.assertIsNone(result["source"])


if __name__ == "__main__":
    unittest.main()
