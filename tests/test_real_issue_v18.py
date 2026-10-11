"""Frozen-v0.18 evaluation safety and task-level evidence checks."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.real_issue_v18 import (
    MAX_PATCH_BYTES, _test_commands, execute_task, grade, manifest, prompt, run_arm,
)
from nykra.v18_report import summarize


class V18Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.digest = manifest()

    def test_cross_repository_frozen_protocol(self):
        tasks = self.config["tasks"]
        self.assertEqual(len(tasks), 4)
        self.assertEqual({t["project"] for t in tasks}, {"youtube-dl", "PySnooper"})
        self.assertEqual(self.config["max_attempts_per_arm"], 3)
        self.assertEqual([t["arm_order"] for t in tasks],
                         [["baseline", "nykra"], ["nykra", "baseline"],
                          ["baseline", "nykra"], ["nykra", "baseline"]])
        self.assertEqual(len(self.digest), 64)

    def test_hidden_selectors_are_not_public(self):
        for t in self.config["tasks"]:
            with self.subTest(task=t["id"]):
                hidden = [v for c in _test_commands(t, "hidden") for v in c]
                self.assertNotIn(t["public_test"], hidden)
                self.assertNotIn("_nykra_private_checks", prompt(t, "def broken(): pass"))
                self.assertNotIn(t["fixed_commit"], prompt(t, "def broken(): pass"))
                for test in t["hidden_upstream_tests"]:
                    self.assertNotIn(test, prompt(t, "def broken(): pass"))

    def test_reject_oversize_before_docker(self):
        with patch("nykra.real_issue_v18.subprocess.run") as execute:
            result = grade(self.config["tasks"][0], mode="public",
                           candidate="x" * (MAX_PATCH_BYTES + 1))
        self.assertEqual(result["status"], "invalid_patch")
        execute.assert_not_called()

    def test_runtime_network_privilege_and_mount_restrictions(self):
        calls=[]
        image=self.config["image_id"]
        def fake(argv, **kwargs):
            calls.append(argv)
            if argv[:3] == ["docker","image","inspect"]:
                return subprocess.CompletedProcess(argv,0,(image+"\n").encode(),b"")
            return subprocess.CompletedProcess(argv,0,b"",b"")
        with patch("nykra.real_issue_v18.build_context"), \
             patch("nykra.real_issue_v18.subprocess.run", side_effect=fake):
            result=grade(self.config["tasks"][0],mode="hidden")
        self.assertTrue(result["passed"])
        run=[c for c in calls if c[:2]==["docker","run"]]
        self.assertEqual(len(run), 2)
        for argv in run:
            for required in ("--network","none","--read-only","--cap-drop","ALL",
                             "--security-opt","no-new-privileges","--user",
                             "--pids-limit","--memory","--cpus","--tmpfs"):
                self.assertIn(required,argv)
            self.assertEqual(argv[argv.index("--user")+1],"65534:65534")
            for forbidden in ("--privileged","-v","--mount","--volume"):
                self.assertNotIn(forbidden,argv)

    def test_requires_approval_and_no_result_overwrite(self):
        task=self.config["tasks"][0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"evidence.json"
            with self.assertRaises(ValueError):
                execute_task(task["id"],p)
            p.write_text("preserved")
            with self.assertRaisesRegex(ValueError,"overwrite"):
                execute_task(task["id"],p,approve=True)
            self.assertEqual(p.read_text(),"preserved")

    def test_hidden_grade_once_only_after_selected_public_success(self):
        grades=[]
        def fake_grade(t,*,mode,candidate=None):
            grades.append(mode)
            return {"status":"ok","passed":True}
        def propose(p,t):
            return {"status":"ok","source":"def cli_bool_option():return []",
                    "tokens":25,"seconds":1}
        with patch("nykra.real_issue_v18.source_bytes",
                   return_value=b"def cli_bool_option():\n    return []\n"), \
             patch("nykra.real_issue_v18.grade",side_effect=fake_grade):
            r=run_arm(self.config["tasks"][0],"nykra",proposer=propose)
        self.assertEqual(grades, ["public", "hidden"])
        self.assertTrue(r["full_success"])
        self.assertEqual(r["attempts_used"], 1)

    def test_token_cap_stops_following_attempts(self):
        model_calls=[]
        def propose(p,t):
            model_calls.append(1)
            return {"status":"ok","source":"def cli_bool_option():return None",
                    "tokens":self.config["soft_reported_token_budget_per_arm"]+1,
                    "seconds":1}
        with patch("nykra.real_issue_v18.source_bytes",
                   return_value=b"def cli_bool_option():\n    return []\n"), \
             patch("nykra.real_issue_v18.grade",
                   return_value={"status":"test_failed","passed":False}):
            r=run_arm(self.config["tasks"][0],"baseline",proposer=propose)
        self.assertEqual(len(model_calls),1)
        self.assertEqual(r["stop_reason"],"token_budget_reached")
        self.assertFalse(r["full_success"])

    def test_saved_raw_evidence_recomputes_actual_null(self):
        s=summarize()
        self.assertEqual(s["registered"],4)
        self.assertEqual(s["paired_completed"],4)
        self.assertEqual(s["prevalidation_excluded"],0)
        self.assertEqual(s["successes"],{"baseline":2,"nykra":2})
        self.assertEqual(s["nykra_only"],1)
        self.assertEqual(s["baseline_only"],1)
        self.assertEqual(s["policy_decision_divergences"],0)
        self.assertFalse(s["general_coding_agent_improvement_proven"])
        self.assertFalse(s["causal_policy_uplift_proven"])


if __name__ == "__main__":
    unittest.main()
