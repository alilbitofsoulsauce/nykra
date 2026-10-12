"""Post-proposal robustness verifier. Not used as agent public feedback."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nykra import transactional_patch as tx
from nykra import multifile_workflow as mw

DIFF=("diff --git a/a.py b/a.py\n"
"--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n")

def fake(count,exit_code=0,extra=b""):
    report=(b"----------------------------------------------------------------------\r\n"+
            f"Ran {count} {'test' if count==1 else 'tests'} in 0.004s\r\n".encode()+
            (b"\r\nOK\r\n" if exit_code==0 else b"\r\nFAILED\r\n"))
    return subprocess.CompletedProcess(["python"],exit_code,b"ignored\n",extra+report)

def tx_trial(returncode,stderr):
    patch_text=DIFF
    with patch.object(tx,"_repository",return_value=(Path("/repo"),"abc")), \
         patch.object(tx,"_preflight"), \
         patch.object(tx,"_trial",return_value=(Path("/repo"),Path("/tmp/patch"),{"a.py":{"operation":"modify"}})), \
         patch.object(tx,"_run_docker",return_value=subprocess.CompletedProcess(["python"],returncode,b"",stderr)):
        return tx.run_transaction("/repo",patch_text,allowed_paths=("a.py",),
                                  docker_image_id="sha256:"+"a"*64,approve=True)

class HiddenTransactionCases(unittest.TestCase):
    def test_single_case_singular_with_crlf(self):
        r=tx_trial(0,fake(1).stderr)
        self.assertTrue(r["tests_passed"])
        self.assertEqual(r["tests_run"],1)
    def test_warning_flood_does_not_hide_summary(self):
        r=tx_trial(0,fake(4,extra=b"warning\n"*500).stderr)
        self.assertTrue(r["tests_passed"])
        self.assertEqual(r["tests_run"],4)
    def test_no_runner_summary_cannot_be_approved(self):
        r=tx_trial(0,b"application exited normally\n")
        self.assertFalse(r["tests_passed"])
        self.assertEqual(r["tests_run"],0)
    def test_status_nonzero_always_fails_with_nonzero_count(self):
        r=tx_trial(3,fake(2,exit_code=3).stderr)
        self.assertFalse(r["tests_passed"])
        self.assertEqual(r["tests_run"],2)
    def test_zero_count_must_fail_despite_ok_exit(self):
        r=tx_trial(0,fake(0).stderr)
        self.assertFalse(r["tests_passed"])
    def test_trailing_zero_summary_overrides_earlier_matching_line(self):
        report=fake(4).stderr+fake(0).stderr
        r=tx_trial(0,report)
        self.assertEqual(r["tests_run"],0)
        self.assertFalse(r["tests_passed"])
    def test_false_stdout_claim_does_not_verify(self):
        r=tx_trial(0,b"")
        self.assertFalse(r["tests_passed"])

class HiddenSupervisorCases(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="nykra-private-")
        self.addCleanup(temp.cleanup)
        self.home=Path(temp.name)
        with patch.object(mw,"_repository",return_value=(Path("/repo"),"abc")):
            self.session=mw.start(repository="/repo",task="host verifier",allowed_paths=("a.py",),
                                  approve=True,home=self.home,docker_image_id="sha256:"+"b"*64)["session_id"]
    def submit(self,resp):
        with patch.object(mw,"_repository",return_value=(Path("/repo"),"abc")), \
             patch.object(mw,"run_transaction",return_value=resp):
            return mw.submit(self.session,DIFF,approve=True,home=self.home)
    def receipt(self,count=1,passed=True):
        return {"tests_run":count,"tests_passed":passed,"test_exit_code":0 if passed else 1,
                "file_count":1,"test_stderr_preview":f"Ran {count} tests in 0.01s",
                "test_stdout_sha256":"f"*64,"test_stderr_sha256":"e"*64,"elapsed_seconds":0.5}
    def test_do_not_trust_boolean_count(self):
        r=self.receipt(count=True,passed=True)
        with self.assertRaisesRegex(ValueError,"test count"):
            self.submit(r)
        self.assertEqual(mw.summary(self.session,home=self.home)["attempts"],[])
    def test_negative_count_must_reject(self):
        with self.assertRaisesRegex(ValueError,"test count"):
            self.submit(self.receipt(count=-2))
        self.assertEqual(mw.summary(self.session,home=self.home)["attempts"],[])
    def test_claimed_pass_with_zero_count_must_reject(self):
        with self.assertRaisesRegex(ValueError,"zero test count"):
            self.submit(self.receipt(count=0))
    def test_zero_case_failure_reported_to_agent(self):
        out=self.submit(self.receipt(count=0,passed=False))
        self.assertEqual(out["evaluated"]["status"],"no_tests")
        self.assertFalse(out["evaluated"]["tests_passed"])
        self.assertEqual(out["next"]["parent_public_feedback"]["status"],"no_tests")
    def test_nonzero_public_failure_is_different_from_no_tests(self):
        out=self.submit(self.receipt(count=2,passed=False))
        self.assertEqual(out["evaluated"]["status"],"test_failed")
        self.assertEqual(out["evaluated"]["tests_run"],2)
