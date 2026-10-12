"""Dependency-free regression suite for supervised real Git multi-file workflows."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import multifile_workflow as mw
from nykra.transactional_patch import PatchRejected


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class MultiFileWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="nykra-multi-workflow-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "home"
        self.repo = Path(temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "core.autocrlf", "false")
        for d in ("engine", "tests"):
            (self.repo / d).mkdir()
            (self.repo / d / "__init__.py").write_text("")
        (self.repo / "engine/calc.py").write_text(
            "def total(a, b):\n    return a - b\n", encoding="utf-8")
        (self.repo / "engine/routes.py").write_text(
            "from engine.calc import total\n"
            "def invoice(a, b):\n    return str(total(a, b) - 1)\n", encoding="utf-8")
        (self.repo / "tests/test_invoice.py").write_text(
            "import unittest\nfrom engine.calc import total\n"
            "from engine.routes import invoice\n"
            "class InvoiceTest(unittest.TestCase):\n"
            "    def test_math(self): self.assertEqual(total(7, 5), 12)\n"
            "    def test_route(self): self.assertEqual(invoice(7, 5), '12')\n",
            encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "Seed buggy Git repository")
        self.head = git(self.repo, "rev-parse", "HEAD").strip()
        (self.repo / "engine/calc.py").write_text(
            "def total(a, b):\n    return a + b\n", encoding="utf-8")
        (self.repo / "engine/routes.py").write_text(
            "from engine.calc import total\n"
            "def invoice(a, b):\n    return str(total(a, b))\n", encoding="utf-8")
        self.patch = git(self.repo, "diff", "--", "engine/calc.py",
                         "engine/routes.py").replace("\r\n", "\n")
        git(self.repo, "checkout", "--", "engine/calc.py", "engine/routes.py")
        self.paths = ("engine/calc.py", "engine/routes.py")

    def start(self, **updates):
        args = dict(repository=self.repo, task="Repair totals and invoice formatting",
                    allowed_paths=self.paths, policy="depth", budget=3,
                    trusted_local_tests=True, approve=True, home=self.home)
        args.update(updates)
        return mw.start(**args)

    def assert_untouched(self):
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertIn("a - b", (self.repo / "engine/calc.py").read_text())

    def test_two_file_success_and_restart_then_finalize_never_promotes(self):
        request = self.start()
        session = request["session_id"]
        self.assertEqual(request["next_attempt"], 1)
        self.assertFalse(request["model_invocation"])
        submitted = mw.submit(session, self.patch, approve=True, home=self.home)
        self.assertTrue(submitted["evaluated"]["tests_passed"])
        self.assertEqual(submitted["evaluated"]["file_count"], 2)
        self.assertFalse(submitted["next"]["agent_required"])
        self.assert_untouched()
        done = mw.finalize(session, approve=True, home=self.home)
        self.assertTrue(done["public_tests_passed"])
        self.assertFalse(done["hidden_verified"])
        self.assertEqual(done["hidden_evaluations"], 0)
        self.assertFalse(done["promoted"])
        self.assertEqual(Path(done["selected_patch_file"]).read_text(), self.patch)
        self.assert_untouched()
        with self.assertRaisesRegex(ValueError, "already"):
            mw.finalize(session, approve=True, home=self.home)

    def test_failed_partial_fix_uses_real_feedback_and_parent(self):
        session = self.start()["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        first = mw.submit(session, part, home=self.home, approve=True)
        self.assertFalse(first["evaluated"]["tests_passed"])
        self.assertEqual(first["next"]["action"]["kind"], "revise")
        self.assertEqual(first["next"]["action"]["parent_attempt_id"], "attempt-1")
        self.assertEqual(first["next"]["parent_public_feedback"]["status"], "test_failed")
        self.assertIn("FAILED", first["next"]["parent_public_feedback"]["diagnostic"])
        self.assert_untouched()
        second = mw.submit(session, self.patch, home=self.home, approve=True)
        self.assertTrue(second["evaluated"]["tests_passed"])
        self.assertEqual(mw.summary(session, home=self.home)["attempts"][1]["parent_attempt_id"],
                         "attempt-1")
        self.assert_untouched()

    def test_invalid_patch_costs_attempt_without_executing(self):
        # Wrong allowlist is rejected before any Git/Docker evaluation.
        session2 = self.start(budget=1, allowed_paths=("engine/calc.py",))["session_id"]
        with patch.object(mw, "run_transaction") as runner:
            invalid = mw.submit(session2, self.patch, approve=True, home=self.home)
        runner.assert_not_called()
        self.assertEqual(invalid["evaluated"]["status"], "invalid_patch")
        self.assertFalse(invalid["next"]["agent_required"])
        self.assert_untouched()

    def test_default_refuses_unpinned_docker_and_unapproved_calls(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            self.start(approve=False)
        with self.assertRaisesRegex(ValueError, "pinned"):
            self.start(trusted_local_tests=False)
        with self.assertRaisesRegex(ValueError, "either"):
            self.start(docker_image_id="sha256:" + "a" * 64)
        request = self.start()
        session = request["session_id"]
        with self.assertRaisesRegex(ValueError, "approval"):
            mw.submit(session, self.patch, home=self.home)
        with self.assertRaisesRegex(ValueError, "approval"):
            mw.finalize(session, home=self.home)
        self.assertEqual(mw.summary(session, home=self.home)["attempts"], [])

    def test_stale_head_dirty_repo_and_infrastructure_failure_preserve_attempt_budget(self):
        session = self.start()["session_id"]
        (self.repo / "untracked.txt").write_text("developer data")
        with self.assertRaisesRegex(PatchRejected, "clean"):
            mw.submit(session, self.patch, approve=True, home=self.home)
        (self.repo / "untracked.txt").unlink()
        with patch.object(mw, "run_transaction",
                          side_effect=PatchRejected("pinned Docker test image unavailable")):
            with self.assertRaisesRegex(PatchRejected, "unavailable"):
                mw.submit(session, self.patch, approve=True, home=self.home)
        self.assertEqual(len(mw.summary(session, home=self.home)["attempts"]), 0)
        (self.repo / "marker.txt").write_text("new version")
        git(self.repo, "add", "marker.txt")
        git(self.repo, "commit", "-qm", "Changed revision")
        with self.assertRaisesRegex(ValueError, "HEAD differs"):
            mw.submit(session, self.patch, approve=True, home=self.home)

    def test_zero_discovered_tests_never_counts_as_success(self):
        (self.repo / "tests/test_invoice.py").write_text("import unittest\n")
        git(self.repo, "add", "tests/test_invoice.py")
        git(self.repo, "commit", "-qm", "Remove public test cases")
        session = self.start()["session_id"]
        try:
            actual = mw.submit(session, self.patch, approve=True, home=self.home)
        except ValueError as exc:
            # Some unittest versions exit 0 with no tests; reject that too.
            self.assertIn("nonzero unittest", str(exc))
        else:
            # Python 3.13's unittest instead returns exit code 5.
            self.assertFalse(actual["evaluated"]["tests_passed"])
            self.assertNotEqual(actual["evaluated"]["test_exit_code"], 0)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        # Older/faulty evaluators might return exit 0 for zero tests; the
        # workflow must still refuse to credit the claimed passing repair.
        second = self.start()["session_id"]
        with patch.object(mw, "run_transaction", return_value={
                "tests_passed": True, "test_exit_code": 0,
                "test_stderr_preview": "Ran 0 tests in 0.001s"}):
            with self.assertRaisesRegex(ValueError, "nonzero unittest"):
                mw.submit(second, self.patch, approve=True, home=self.home)
        self.assertEqual(mw.summary(second, home=self.home)["attempts"], [])

    def test_adaptive_policy_restarts_after_three_public_failures(self):
        session = self.start(policy="adaptive", budget=4)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        for i in range(3):
            result = mw.submit(session, part, approve=True, home=self.home)
            self.assertFalse(result["evaluated"]["tests_passed"])
        self.assertEqual(result["next"]["action"],
                         {"kind": "new_root", "parent_attempt_id": None})
        completed = mw.submit(session, self.patch, approve=True, home=self.home)
        self.assertTrue(completed["evaluated"]["tests_passed"])
        self.assertEqual(completed["evaluated"]["action"], "new_root")
        self.assert_untouched()

    def test_invalid_session_identity_and_owner(self):
        with self.assertRaisesRegex(ValueError, "ID"):
            mw.next_request("../unsafe", home=self.home)
        session = self.start()["session_id"]
        marker = mw._folder(session, self.home) / "OWNER"
        marker.write_text("spoofed", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "ownership"):
            mw.next_request(session, home=self.home)
        self.assert_untouched()

    def test_cross_process_cli_and_abort(self):
        def cli(*args):
            result = subprocess.run(
                [sys.executable, "-m", "nykra", "--home", str(self.home),
                 "multi-workflow", *args],
                capture_output=True, text=True, encoding="utf-8", timeout=50)
            return result
        start_args = ("start", "--repository", str(self.repo), "--task", "Fix two files",
                      "--allow", "engine/calc.py", "--allow", "engine/routes.py",
                      "--trusted-local-tests")
        unapproved = cli(*start_args)
        self.assertNotEqual(unapproved.returncode, 0)
        create = cli(*start_args, "--approve")
        self.assertEqual(create.returncode, 0, create.stderr)
        session = json.loads(create.stdout)["session_id"]
        patch_file = self.home / "proposed.diff"
        patch_file.write_text(self.patch, encoding="utf-8")
        denied = cli("submit", "--session", session, "--candidate-file", str(patch_file))
        self.assertNotEqual(denied.returncode, 0)
        tested = cli("submit", "--session", session, "--candidate-file", str(patch_file),
                     "--approve")
        self.assertEqual(tested.returncode, 0, tested.stderr)
        self.assertTrue(json.loads(tested.stdout)["evaluated"]["tests_passed"])
        done = cli("finalize", "--session", session, "--approve")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(json.loads(done.stdout)["promoted"])
        self.assert_untouched()
        session2 = self.start()["session_id"]
        self.assertEqual(mw.abort(session2, approve=True, home=self.home)["status"], "aborted")
        with self.assertRaisesRegex(ValueError, "finished"):
            mw.submit(session2, self.patch, approve=True, home=self.home)

    def test_optin_exact_failed_patch_reuses_receipt_not_public_executor(self):
        session = self.start(dedupe_public=True, budget=3)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        with patch.object(mw, "run_transaction", wraps=mw.run_transaction) as worker:
            first = mw.submit(session, part, approve=True, home=self.home)
            second = mw.submit(session, part, approve=True, home=self.home)
        self.assertEqual(worker.call_count, 1)
        first_attempt, again = first["evaluated"], second["evaluated"]
        self.assertFalse(first_attempt["public_test_reused"])
        self.assertTrue(again["public_test_reused"])
        self.assertEqual(again["reused_from_attempt_id"], "attempt-1")
        self.assertEqual(first_attempt["patch_sha256"], again["patch_sha256"])
        self.assertEqual(first_attempt["status"], again["status"])
        self.assertEqual(first_attempt["diagnostic"], again["diagnostic"])
        self.assertEqual(first_attempt["tests_run"], again["tests_run"])
        self.assertEqual(again["public_tests_executed_now"], 0)
        self.assertEqual(second["public_work"], {
            "public_evaluator_calls": 1, "public_evaluator_reuses": 1,
            "model_attempts_recorded": 2,
        })
        self.assertEqual(second["next"]["next_attempt"], 3)
        self.assertEqual(second["next"]["action"]["parent_attempt_id"], "attempt-2")
        attempt_files = sorted(mw._folder(session, self.home).glob("attempt-*.diff"))
        self.assertEqual(len(attempt_files), 2)
        self.assertEqual(attempt_files[0].read_bytes(), attempt_files[1].read_bytes())
        self.assert_untouched()

    def test_default_duplicate_does_not_reuse_any_public_receipt(self):
        session = self.start(dedupe_public=False, budget=2)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        with patch.object(mw, "run_transaction", wraps=mw.run_transaction) as worker:
            first = mw.submit(session, part, approve=True, home=self.home)
            second = mw.submit(session, part, approve=True, home=self.home)
        self.assertEqual(worker.call_count, 2)
        self.assertFalse(second["evaluated"]["public_test_reused"])
        self.assertEqual(second["public_work"]["public_evaluator_calls"], 2)
        self.assertEqual(second["public_work"]["public_evaluator_reuses"], 0)
        self.assert_untouched()

    def test_optin_different_patch_is_evaluated_and_can_win(self):
        session = self.start(dedupe_public=True)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        with patch.object(mw, "run_transaction", wraps=mw.run_transaction) as worker:
            first = mw.submit(session, part, approve=True, home=self.home)
            second = mw.submit(session, self.patch, approve=True, home=self.home)
        self.assertFalse(first["evaluated"]["tests_passed"])
        self.assertTrue(second["evaluated"]["tests_passed"])
        self.assertEqual(worker.call_count, 2)
        self.assertFalse(second["evaluated"]["public_test_reused"])
        final = mw.finalize(session, approve=True, home=self.home)
        self.assertTrue(final["public_tests_passed"])
        self.assertEqual(final["public_work"]["public_evaluator_calls"], 2)
        self.assertEqual(final["public_work"]["public_evaluator_reuses"], 0)
        self.assert_untouched()

    def test_optin_dirty_repo_is_refused_on_cache_hit(self):
        session = self.start(dedupe_public=True)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        mw.submit(session, part, approve=True, home=self.home)
        dirty = self.repo / "untracked-secret.txt"
        dirty.write_text("untracked content")
        with patch.object(mw, "run_transaction") as worker:
            with self.assertRaisesRegex(PatchRejected, "clean"):
                mw.submit(session, part, approve=True, home=self.home)
            worker.assert_not_called()
        self.assertEqual(len(mw.summary(session, home=self.home)["attempts"]), 1)
        dirty.unlink()
        self.assert_untouched()

    def test_optin_modified_cached_diff_rechecks_instead_of_reusing(self):
        session = self.start(dedupe_public=True)["session_id"]
        part = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        mw.submit(session, part, approve=True, home=self.home)
        saved = mw._folder(session, self.home) / "attempt-1.diff"
        saved.write_text("intentionally tampered")
        with patch.object(mw, "run_transaction", wraps=mw.run_transaction) as worker:
            again = mw.submit(session, part, approve=True, home=self.home)
        self.assertEqual(worker.call_count, 1)
        self.assertFalse(again["evaluated"]["public_test_reused"])
        self.assertEqual(again["public_work"]["public_evaluator_calls"], 2)
        self.assert_untouched()

    def test_optin_invalid_repeated_patch_cannot_be_cached(self):
        session = self.start(dedupe_public=True, budget=2,
                             allowed_paths=("engine/calc.py",))["session_id"]
        with patch.object(mw, "run_transaction") as worker:
            first = mw.submit(session, self.patch, approve=True, home=self.home)
            second = mw.submit(session, self.patch, approve=True, home=self.home)
        worker.assert_not_called()
        self.assertEqual(first["evaluated"]["status"], "invalid_patch")
        self.assertEqual(second["evaluated"]["status"], "invalid_patch")
        self.assertFalse(second["evaluated"]["public_test_reused"])
        self.assertEqual(second["public_work"]["public_evaluator_reuses"], 0)
        self.assertEqual(second["public_work"]["model_attempts_recorded"], 2)

    def test_optin_docker_receipt_replayed_without_second_docker_call(self):
        fake = {
            "tests_passed": False, "tests_run": 6,
            "test_exit_code": 1, "test_stderr_preview": "Ran 6 tests; FAILED",
            "file_count": 2, "test_stdout_sha256": "a" * 64,
            "test_stderr_sha256": "b" * 64, "elapsed_seconds": 9.75,
        }
        session = self.start(dedupe_public=True, budget=3,
                             trusted_local_tests=False,
                             docker_image_id="sha256:" + "c" * 64)["session_id"]
        with patch.object(mw, "run_transaction", return_value=fake) as worker:
            first = mw.submit(session, self.patch, approve=True, home=self.home)
            second = mw.submit(session, self.patch, approve=True, home=self.home)
        worker.assert_called_once()
        self.assertEqual(worker.call_args.kwargs["executor"], "docker")
        self.assertEqual(first["evaluated"]["tests_run"], 6)
        self.assertEqual(second["evaluated"]["tests_run"], 6)
        self.assertEqual(second["evaluated"]["public_tests_executed_now"], 0)
        self.assertTrue(second["evaluated"]["public_test_reused"])
        self.assertEqual(second["evaluated"]["elapsed_seconds"], 0.0)
        self.assertEqual(second["public_work"]["public_evaluator_calls"], 1)
        self.assert_untouched()

    def test_optin_zero_test_failure_is_not_misreported_as_success(self):
        fake = {
            "tests_passed": False, "tests_run": 0,
            "test_exit_code": 5, "test_stderr_preview": "Ran 0 tests",
            "file_count": 2, "test_stdout_sha256": "a" * 64,
            "test_stderr_sha256": "b" * 64, "elapsed_seconds": 2.0,
        }
        session = self.start(dedupe_public=True, budget=2)["session_id"]
        with patch.object(mw, "run_transaction", return_value=fake) as worker:
            one = mw.submit(session, self.patch, approve=True, home=self.home)
            two = mw.submit(session, self.patch, approve=True, home=self.home)
        worker.assert_called_once()
        self.assertEqual(one["evaluated"]["status"], "no_tests")
        self.assertEqual(two["evaluated"]["status"], "no_tests")
        self.assertTrue(two["evaluated"]["public_test_reused"])
        self.assertFalse(mw.finalize(session, home=self.home, approve=True)["public_tests_passed"])

    def test_optin_rejects_nonbool_and_cross_process_setting_is_durable(self):
        with self.assertRaisesRegex(ValueError, "flags"):
            self.start(dedupe_public=1)
        created = self.start(dedupe_public=True)
        session = created["session_id"]
        command = [sys.executable, "-m", "nykra", "--home", str(self.home),
                   "multi-workflow", "summary", "--session", session]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dedupe_public"])

    def test_optin_repeat_failure_halts_new_model_request_after_two_same_fails(self):
        session = self.start(halt_on_repeat_failure=True, budget=4)["session_id"]
        partial = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        first = mw.submit(session, partial, approve=True, home=self.home)
        self.assertTrue(first["next"]["agent_required"])
        second = mw.submit(session, partial, approve=True, home=self.home)
        self.assertFalse(second["evaluated"]["tests_passed"])
        gate = second["next"]
        self.assertEqual(gate["status"], "paused_repeated_failed_patch")
        self.assertFalse(gate["agent_required"])
        self.assertFalse(gate["model_invocation"])
        self.assertEqual(gate["remaining_attempts"], 2)
        self.assertTrue(mw.summary(session, home=self.home)["model_request_paused"])
        with patch.object(mw, "run_transaction") as evaluator:
            with self.assertRaisesRegex(ValueError, "repeat-stalled"):
                mw.submit(session, self.patch, approve=True, home=self.home)
            evaluator.assert_not_called()
        final = mw.finalize(session, home=self.home, approve=True)
        self.assertTrue(final["paused_before_finalization"])
        self.assertFalse(final["public_tests_passed"])
        self.assertFalse(final["promoted"])
        self.assert_untouched()

    def test_repeat_failure_guard_is_off_by_default(self):
        session = self.start(budget=4)["session_id"]
        partial = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        mw.submit(session, partial, approve=True, home=self.home)
        second = mw.submit(session, partial, approve=True, home=self.home)
        self.assertTrue(second["next"]["agent_required"])
        self.assertEqual(second["next"]["action"]["kind"], "revise")
        self.assertFalse(mw.summary(session, home=self.home)["model_request_paused"])
        self.assert_untouched()

    def test_repeat_failure_guard_different_patch_does_not_halt(self):
        session = self.start(halt_on_repeat_failure=True, budget=4)["session_id"]
        partial = self.patch[:self.patch.find("diff --git a/engine/routes.py")]
        variant = partial.replace("return a + b", "return a + b + 1")
        mw.submit(session, partial, approve=True, home=self.home)
        second = mw.submit(session, variant, approve=True, home=self.home)
        self.assertFalse(second["evaluated"]["tests_passed"])
        self.assertTrue(second["next"]["agent_required"])
        self.assertFalse(mw.summary(session, home=self.home)["model_request_paused"])
        self.assert_untouched()

    def test_repeat_failure_guard_with_dedupe_reuses_one_docker_receipt_then_halts(self):
        fake = {"tests_passed": False, "tests_run": 6, "test_exit_code": 1,
                "test_stderr_preview": "Ran 6 tests; FAILED", "file_count": 2,
                "test_stdout_sha256": "a"*64, "test_stderr_sha256": "b"*64,
                "elapsed_seconds": 3.0}
        session = self.start(dedupe_public=True, halt_on_repeat_failure=True,
                             trusted_local_tests=False,
                             docker_image_id="sha256:" + "c"*64,
                             budget=4)["session_id"]
        with patch.object(mw, "run_transaction", return_value=fake) as evaluator:
            mw.submit(session, self.patch, approve=True, home=self.home)
            second = mw.submit(session, self.patch, approve=True, home=self.home)
            self.assertEqual(evaluator.call_count, 1)
        self.assertTrue(second["evaluated"]["public_test_reused"])
        self.assertFalse(second["next"]["agent_required"])
        self.assertEqual(second["next"]["status"], "paused_repeated_failed_patch")
        self.assertEqual(second["public_work"]["model_attempts_recorded"], 2)
        self.assertEqual(second["public_work"]["public_evaluator_calls"], 1)
        self.assertEqual(second["public_work"]["public_evaluator_reuses"], 1)
        self.assert_untouched()

    def test_repeat_failure_guard_nonboolean_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "flags"):
            self.start(halt_on_repeat_failure=1)

    def test_repeat_failure_guard_cross_process_cli_accepts_optin(self):
        proc = subprocess.run(
            [sys.executable, "-m", "nykra", "--home", str(self.home),
             "multi-workflow", "start", "--repository", str(self.repo),
             "--task", "Invoice source repair",
             "--allow", "engine/calc.py", "--allow", "engine/routes.py",
             "--policy", "adaptive", "--budget", "4", "--trusted-local-tests",
             "--halt-on-repeat-failure", "--approve"],
            capture_output=True, text=True, encoding="utf-8", timeout=35)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        started = json.loads(proc.stdout)
        self.assertTrue(started["halt_on_repeat_failure"])
        self.assertTrue(started["agent_required"])
        self.assert_untouched()


if __name__ == "__main__":
    unittest.main()
