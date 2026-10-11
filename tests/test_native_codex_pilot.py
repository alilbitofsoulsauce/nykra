"""Native Codex pilot controls: disjoint evaluation, honest missing-runner behavior."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.native_codex_pilot import (
    invoke_model, prompt_for, run_arm, run_task, score_source,
)
from nykra.repair_tasks import TASKS, cases, oracle

CORRECT_PATH = (
    "def solve(base, relative):\n"
    "    if relative[:1] == '/' or '\\\\' in relative:\n"
    "        return None\n"
    "    parts = []\n"
    "    section = ''\n"
    "    for ch in relative + '/':\n"
    "        if ch == '/':\n"
    "            if section == '..':\n"
    "                if not parts:\n"
    "                    return None\n"
    "                parts = parts[:-1]\n"
    "            elif section and section != '.':\n"
    "                parts = parts + [section]\n"
    "            section = ''\n"
    "        else:\n"
    "            section = section + ch\n"
    "    if not parts:\n"
    "        return base\n"
    "    result = '' if base == '/' else base\n"
    "    for ch in parts:\n"
    "        result = result + '/' + ch\n"
    "    return result\n"
)
BAD_PATH = "def solve(base, relative):\n    return base + '/' + relative\n"


class NativeCodexPilotTests(unittest.TestCase):
    def test_disjoint_fixed_hidden_cases_and_reference_oracle(self):
        for task in TASKS:
            with self.subTest(task=task):
                public = cases(task, heldout=False)
                hidden = cases(task, heldout=True)
                self.assertEqual(len(public), 14)
                self.assertEqual(len(hidden), 32)
                source = {json.dumps(v[0], sort_keys=True, ensure_ascii=False) for v in public}
                unseen = {json.dumps(v[0], sort_keys=True, ensure_ascii=False) for v in hidden}
                self.assertFalse(source.intersection(unseen))
                self.assertEqual(len(unseen), 32)
                for arguments, expected in public + hidden:
                    self.assertEqual(expected, oracle(task, arguments))

    def test_rejects_broken_candidate_and_accepts_solved_path(self):
        wrong = score_source("normalized-path", BAD_PATH, heldout=False)
        self.assertLess(wrong["score"], 1)
        good = score_source("normalized-path", CORRECT_PATH, heldout=False)
        self.assertEqual(good["score"], 1, good)
        heldout = score_source("normalized-path", CORRECT_PATH, heldout=True)
        self.assertEqual(heldout["score"], 1)
        self.assertEqual(heldout["failure_examples"], [])

    def test_model_unavailable_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            resp = invoke_model("test", executable=Path(temporary, "missing.exe"), timeout=2)
        self.assertEqual(resp["status"], "model_binary_missing")
        self.assertIsNone(resp["source"])

    def test_baseline_and_guided_receive_same_public_feedback(self):
        previous = BAD_PATH
        feedback = score_source("normalized-path", BAD_PATH, heldout=False)
        base = prompt_for("normalized-path", previous=previous, training=feedback, guided=False)
        nykra = prompt_for("normalized-path", previous=previous, training=feedback, guided=True)
        self.assertIn(previous, base)
        self.assertIn(previous, nykra)
        self.assertIn("failure_examples", base)
        self.assertIn("failure_examples", nykra)
        self.assertIn("fresh, independent", base)
        self.assertIn("Revise the previous", nykra)
        self.assertNotIn("heldout", nykra.lower())

    def test_record_failed_model_call_no_hidden_success(self):
        fake = {"status": "model_failed", "elapsed_seconds": 0.1,
                "source": None, "tokens_reported": None}
        with patch("nykra.native_codex_pilot.invoke_model", return_value=fake):
            res = run_arm("normalized-path", "nykra", executable=Path("nonexistent"), timeout=1)
        self.assertFalse(res["final_heldout_success"])
        self.assertEqual(res["attempts_used"], 1)
        self.assertEqual(res["final_heldout_passed"], 0)

    def test_task_requires_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                run_task("normalized-path", output=Path(temporary, "out.json"))


if __name__ == "__main__":
    unittest.main()
