"""Native IDE extension + local-only inbox end-to-end integration tests."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from nykra import __version__
from nykra.ide import detect_ides, manage_extension, package_vsix
from nykra.ide_inbox import drain_ide_inbox
from nykra.store import HistoryStore
from nykra.workstation import run_runtime


ROOT = Path(__file__).resolve().parents[1]


class IDEIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nykra-ide-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "nykra"
        self.store = HistoryStore(self.home)

    def test_extension_package_is_self_contained(self):
        destination = self.base / "nykra-observer.vsix"
        pkg = package_vsix(destination)
        self.assertTrue(pkg.is_file())
        with zipfile.ZipFile(pkg) as archive:
            names = archive.namelist()
            self.assertIn("extension.vsixmanifest", names)
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("extension/package.json", names)
            self.assertIn("extension/extension.js", names)
            meta = json.loads(archive.read("extension/package.json"))
            self.assertEqual(meta["publisher"] + "." + meta["name"], "nykra.nykra-observer")
            self.assertEqual(meta["version"], __version__)
            self.assertEqual(meta["extensionKind"], ["ui"])
            self.assertIn("onStartupFinished", meta["activationEvents"])
            self.assertIn("Microsoft.VisualStudio.Code.Manifest", archive.read("extension.vsixmanifest").decode())

    @unittest.skipUnless(shutil.which("node"), "Node required to validate IDE extension")
    def test_synthetic_vscode_activity_reaches_running_nykra(self):
        inbox = self.home / "ide-inbox"
        env = os.environ.copy()
        env["NYKRA_TEST_INBOX"] = str(inbox)
        process = subprocess.run(
            ["node", "tests/ide_mock.cjs"], cwd=ROOT,
            env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stdout + "\n" + process.stderr)
        self.assertEqual(len(list(inbox.glob("*.json"))), 2)
        # No Rel.AI database is available: the IDE intake must still work.
        result = run_runtime(self.home, source_db=self.base / "missing.sqlite",
                             cycles=1, interval=0.25)
        self.assertFalse(result["source_detected"])
        stats = self.store.stats()
        self.assertEqual(stats["ide_activity_count"], 2)
        self.assertEqual(stats["attempt_count"], 0)
        self.assertEqual(stats["run_count"], 0)
        self.assertEqual(len(list(inbox.glob("*.json"))), 0)
        activities = self.store.list_activity()
        self.assertEqual({r["tool"] for r in activities}, {"document_save", "task_completed"})
        self.assertEqual({r["outcome"] for r in activities}, {"succeeded", "failed"})
        for event in activities:
            payload = json.dumps(event)
            self.assertNotIn("SECRET", payload)
            self.assertNotIn("PRIVATE", payload)
            self.assertTrue(event["task_id"].startswith("ws-"))

    def test_rejects_payload_containing_prompts_or_raw_file_paths(self):
        inbox = self.home / "ide-inbox"
        inbox.mkdir(exist_ok=True)
        clean = {
            "event_id": "ide-" + "a" * 36,
            "source": "ide-cursor",
            "task_id": "ws-" + "a" * 24,
            "tool": "document_save", "outcome": "succeeded", "duration_ms": 0
        }
        bad = dict(clean, event_id="ide-" + "b" * 36, prompt="PRIVATE_PROMPT")
        (inbox / "good.json").write_text(json.dumps(clean), encoding="utf-8")
        (inbox / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        result = drain_ide_inbox(self.store)
        self.assertEqual(result["ingested"], 1)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(self.store.stats()["ide_activity_count"], 1)
        self.assertEqual(list(inbox.glob("*.json")), [])

    def test_supported_ide_detection_does_not_infer_from_profile_directory(self):
        with patch("nykra.ide._candidates", return_value=[]):
            result = detect_ides()
        self.assertEqual({r["id"] for r in result}, {"vscode", "cursor", "windsurf", "vscodium"})
        self.assertTrue(all(not r["cli_detected"] for r in result))

    def test_manage_install_without_cli_has_no_side_effects(self):
        with patch("nykra.ide._candidates", return_value=[]):
            result = manage_extension("install")
        self.assertFalse(result["changed"])
        self.assertEqual(result["outcome"], "no_compatible_editor_cli_detected")

    def test_manage_uninstall_runs_only_namespaced_extension(self):
        fake_cli = self.base / "code.cmd"
        fake_cli.write_text("", encoding="utf-8")
        with (patch("nykra.ide._candidates", return_value=[fake_cli]),
              patch("nykra.ide.subprocess.run") as subprocess_run):
            subprocess_run.return_value.returncode = 0
            outcome = manage_extension("uninstall", target="vscode")
            self.assertTrue(outcome["changed"])
            passed = subprocess_run.call_args.args[0]
            self.assertEqual(passed, [str(fake_cli), "--uninstall-extension", "nykra.nykra-observer"])


if __name__ == "__main__":
    unittest.main()
