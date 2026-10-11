"""Adversarial multi-file Git transactions with real tests and rollback semantics."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.transactional_patch import PatchRejected, parse_patch, run_transaction


def git(root, *cmd):
    r=subprocess.run(["git","-C",str(root),*cmd],
                     capture_output=True,check=False,timeout=30)
    if r.returncode:
        raise RuntimeError(r.stderr.decode("utf-8","replace"))
    return r.stdout.decode("utf-8","replace")


class RealMultiFileTransactionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="nykra-hard-real-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"repository"
        self.root.mkdir()
        git(self.root,"init","-q")
        git(self.root,"config","user.name","Nykra Test")
        git(self.root,"config","user.email","tests@example.invalid")
        git(self.root,"config","core.autocrlf","false")
        (self.root/"engine").mkdir()
        (self.root/"tests").mkdir()
        (self.root/"engine/__init__.py").write_text("",encoding="utf-8")
        (self.root/"tests/__init__.py").write_text("",encoding="utf-8")
        (self.root/"engine/calc.py").write_text(
            "def total(a, b):\n    return a - b\n",encoding="utf-8")
        (self.root/"engine/routes.py").write_text(
            "from engine.calc import total\n\n"
            "def invoice_url(a, b):\n"
            "    return '/invoice/' + str(total(a, b) - 1)\n",encoding="utf-8")
        (self.root/"tests/test_invoices.py").write_text(
            "import unittest\nfrom engine.calc import total\n"
            "from engine.routes import invoice_url\n\n"
            "class InvoiceTests(unittest.TestCase):\n"
            "    def test_sum(self):\n"
            "        self.assertEqual(total(7, 5), 12)\n"
            "    def test_route(self):\n"
            "        self.assertEqual(invoice_url(7, 5), '/invoice/12')\n",
            encoding="utf-8")
        git(self.root,"add",".")
        git(self.root,"commit","-qm","Original two independent bugs")
        self.before=git(self.root,"rev-parse","HEAD").strip()
        (self.root/"engine/calc.py").write_text(
            "def total(a, b):\n    return a + b\n",encoding="utf-8")
        (self.root/"engine/routes.py").write_text(
            "from engine.calc import total\n\n"
            "def invoice_url(a, b):\n"
            "    return '/invoice/' + str(total(a, b))\n",encoding="utf-8")
        self.patch=git(self.root,"diff","--","engine/calc.py","engine/routes.py").replace("\r\n","\n")
        git(self.root,"checkout","--","engine/calc.py","engine/routes.py")
        self.allowed=("engine/calc.py","engine/routes.py")
        self.assertEqual(git(self.root,"status","--porcelain"),"")

    def txn(self,patch=None,**kwargs):
        opts=dict(root=self.root,patch=patch if patch is not None else self.patch,
                  allowed_paths=self.allowed,executor="local",
                  allow_trusted_local_tests=True,
                  test_args=("-B","-m","unittest","discover","-s","tests","-v"),
                  approve=True)
        opts.update(kwargs)
        return run_transaction(**opts)

    def test_real_two_file_fix_preview_preserves_original(self):
        r=self.txn()
        self.assertEqual(r["file_count"],2)
        self.assertTrue(r["tests_passed"])
        self.assertFalse(r["promoted"])
        self.assertEqual(r["test_exit_code"],0)
        self.assertEqual(git(self.root,"rev-parse","HEAD").strip(),self.before)
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        self.assertIn("return a - b",(self.root/"engine/calc.py").read_text())
        self.assertIn("- 1",(self.root/"engine/routes.py").read_text())

    def test_approved_promote_changes_both_files_and_preserves_head(self):
        r=self.txn(promote=True)
        self.assertTrue(r["tests_passed"])
        self.assertTrue(r["promoted"])
        self.assertEqual(git(self.root,"rev-parse","HEAD").strip(),self.before)
        self.assertIn("return a + b",(self.root/"engine/calc.py").read_text())
        self.assertNotIn("- 1",(self.root/"engine/routes.py").read_text())
        self.assertEqual(sorted(git(self.root,"diff","--name-only").splitlines()),
                         list(self.allowed))
        self.assertEqual(r["files"]["engine/calc.py"]["operation"],"modify")

    def test_patch_fixing_only_first_bug_fails_no_host_changes(self):
        only_calc=git(self.root,"show","HEAD:engine/calc.py")
        self.assertIn("a - b",only_calc)
        first=self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        r=self.txn(first)
        self.assertFalse(r["tests_passed"])
        self.assertFalse(r["promoted"])
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        self.assertIn("FAILED",r["test_stderr_preview"])

    def test_promote_failure_never_changes_original(self):
        partial=self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        r=self.txn(partial,promote=True)
        self.assertFalse(r["tests_passed"])
        self.assertFalse(r["promoted"])
        self.assertEqual(git(self.root,"status","--porcelain"),"")

    def test_allowlist_rejects_change_before_running_tests(self):
        with self.assertRaisesRegex(PatchRejected,"non-allowlisted"):
            self.txn(allowed_paths=("engine/calc.py",))

    def test_requires_clean_git_checkout(self):
        (self.root/"unexpected.txt").write_text("Don't delete my work")
        with self.assertRaisesRegex(PatchRejected,"clean"):
            self.txn()
        self.assertTrue((self.root/"unexpected.txt").is_file())

    def test_malformed_git_hunk_rejected_without_mutation(self):
        corrupted=self.patch.replace("-    return a - b","-    return a * b")
        with self.assertRaisesRegex(PatchRejected,"Git refused"):
            self.txn(corrupted)
        self.assertEqual(git(self.root,"status","--porcelain"),"")

    def test_explicit_authorization_required(self):
        with self.assertRaisesRegex(PatchRejected,"approval"):
            self.txn(approve=False)
        with self.assertRaisesRegex(PatchRejected,"trust"):
            self.txn(allow_trusted_local_tests=False)
        with self.assertRaisesRegex(PatchRejected,"pinned Docker"):
            self.txn(executor="docker",docker_image_id=None)

    def test_rejects_symlink_targets(self):
        replacement=Path(self.root.parent)/"outside.py"
        replacement.write_text("critical file")
        target=self.root/"engine/calc.py"
        target.unlink()
        try:
            os.symlink(replacement,target)
        except (OSError,NotImplementedError):
            self.skipTest("creating symlink unavailable")
        with self.assertRaises(PatchRejected):
            self.txn()
        self.assertEqual(replacement.read_text(),"critical file")

    def test_refuses_oversized_patch(self):
        with self.assertRaisesRegex(PatchRejected,"too large"):
            self.txn(self.patch + ("#"*150000))

    def test_path_and_mode_attacks(self):
        for path in ("../secret.py","foo/../secret.py",".git/config","CON",
                     "foo//bar.py","C:/Windows/x","foo/./bar.py",
                     "a\\b.py"):
            with self.subTest(path=path):
                self.assertRaises(PatchRejected,parse_patch,self.patch,(path,))
        evil=self.patch.replace("diff --git a/engine/calc.py b/engine/calc.py",
                                "diff --git a/engine/../calc.py b/engine/../calc.py")
        with self.assertRaises(PatchRejected):
            self.txn(evil)
        with self.assertRaises(PatchRejected):
            self.txn(self.patch.replace("index ","old mode 100644\nindex ",1))
        with self.assertRaises(PatchRejected):
            self.txn(self.patch.replace("index ","GIT binary patch\nindex ",1))

    def test_no_hidden_tests_executed_or_stored(self):
        r=self.txn()
        self.assertNotIn("hidden",r)
        self.assertEqual(set(r["files"]),set(self.allowed))

    def test_failure_during_promotion_restores_original_bytes(self):
        # Simulate a post-apply verification exception from a malformed
        # expected source hash and prove rollback of both modified files.
        from nykra import transactional_patch as tx
        original_trial=tx._trial
        def sabotaged(*args,**kwargs):
            checkout,file,changes=original_trial(*args,**kwargs)
            changes["engine/routes.py"]["after_sha256"]="0"*64
            return checkout,file,changes
        with patch.object(tx,"_trial",side_effect=sabotaged):
            with self.assertRaisesRegex(PatchRejected,"tested checkout source changed|promoted file"):
                self.txn(promote=True)
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        self.assertIn("return a - b",(self.root/"engine/calc.py").read_text())


    def test_cli_approval_gated_two_file_preview_and_promotion(self):
        import json
        import sys
        patch_file=self.root.parent/"candidate.diff"
        patch_file.write_text(self.patch,encoding="utf-8")
        command=[sys.executable,"-m","nykra","patch-transaction",
                 "--repository",str(self.root),
                 "--patch-file",str(patch_file),
                 "--allow","engine/calc.py","--allow","engine/routes.py",
                 "--trusted-local-tests"]
        no_auth=subprocess.run(command,capture_output=True,text=True,timeout=45)
        self.assertNotEqual(no_auth.returncode,0)
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        preview=subprocess.run(command+["--approve"],capture_output=True,text=True,
                               encoding="utf-8",timeout=75)
        self.assertEqual(preview.returncode,0,preview.stderr[-700:])
        p=json.loads(preview.stdout)
        self.assertTrue(p["tests_passed"])
        self.assertFalse(p["promoted"])
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        promotion=subprocess.run(command+["--approve","--promote"],
                                 capture_output=True,text=True,encoding="utf-8",timeout=75)
        self.assertEqual(promotion.returncode,0,promotion.stderr[-700:])
        done=json.loads(promotion.stdout)
        self.assertTrue(done["promoted"] and done["tests_passed"])
        self.assertEqual(len(git(self.root,"diff","--name-only").splitlines()),2)

    def test_simple_addition_and_rollback_of_failed_deletion(self):
        extra=(self.root/"engine/new_helpers.py")
        added=("diff --git a/engine/new_helpers.py b/engine/new_helpers.py\n"
               "new file mode 100644\n"
               "--- /dev/null\n"
               "+++ b/engine/new_helpers.py\n"
               "@@ -0,0 +1,2 @@\n"
               "+def square(number):\n"
               "+    return number * number\n")
        result=self.txn(self.patch+added,allowed_paths=(*self.allowed,"engine/new_helpers.py"),promote=True)
        self.assertTrue(result["promoted"] and result["tests_passed"])
        self.assertEqual(extra.read_text().replace("\r\n","\n"),
                         "def square(number):\n    return number * number\n")
        git(self.root,"add","engine/calc.py","engine/routes.py","engine/new_helpers.py")
        git(self.root,"commit","-qm","Add helper for deletion test")
        (self.root/"engine/routes.py").unlink()
        deletion=git(self.root,"diff","--","engine/routes.py").replace("\r\n","\n")
        git(self.root,"checkout","--","engine/routes.py")
        doomed=self.txn(deletion,allowed_paths=("engine/routes.py",),promote=True)
        self.assertFalse(doomed["tests_passed"])
        self.assertFalse(doomed["promoted"])
        self.assertTrue((self.root/"engine/routes.py").is_file())
        self.assertEqual(git(self.root,"status","--porcelain"),"")

if __name__=="__main__":
    unittest.main()
