"""Per-user installation and workstation daemon regression tests."""
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.install import install_user, installed_status, uninstall_user, AUTOSTART_FILENAME
from nykra.store import NykraError
from nykra.workstation import read_health, request_stop, run_runtime, _single_instance, _atomic_json


class WorkstationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nykra-workstation-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "state"
        self.source = Path(self.temp.name) / "relai.sqlite"

    def create_source(self):
        conn = sqlite3.connect(self.source)
        try:
            conn.execute("""CREATE TABLE task_history_events(
                task_id TEXT, event_key TEXT, event_index INTEGER, task_updated_at_ms INTEGER,
                event_timestamp TEXT, payload TEXT
            )""")
            conn.commit()
        finally:
            conn.close()

    def test_waits_for_relai_without_crashing(self):
        result = run_runtime(self.home, source_db=self.source, interval=0.25, cycles=2)
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["source_detected"])
        self.assertEqual(read_health(self.home)["state"], "stopped")

    def test_readonly_source_is_detected(self):
        self.create_source()
        run_runtime(self.home, source_db=self.source, interval=0.25, cycles=2)
        self.assertEqual(read_health(self.home)["state"], "stopped")
        self.assertEqual(json.loads((self.home / "runtime-health.json").read_text())["last_issue"], None)

    def test_stop_is_cooperative_and_instance_scoped(self):
        self.create_source()
        output = []
        thread = threading.Thread(target=lambda: output.append(
            run_runtime(self.home, interval=0.25, source_db=self.source)), daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not read_health(self.home).get("healthy"):
            time.sleep(0.04)
        self.assertTrue(read_health(self.home)["healthy"])
        stopped = request_stop(self.home, timeout=4)
        self.assertTrue(stopped["stopped"])
        thread.join(timeout=4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(read_health(self.home)["state"], "stopped")
        self.assertEqual(len(output), 1)

    def test_atomic_health_retries_transient_sharing_violation(self):
        original = os.replace
        calls = []
        def fail_twice(src, dst):
            calls.append((src, dst))
            if len(calls) <= 2:
                raise PermissionError("simulated transient lock")
            return original(src, dst)
        target = self.home / "runtime-health.json"
        with patch("nykra.workstation.os.replace", side_effect=fail_twice):
            _atomic_json(target, {"healthy": True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads(target.read_text()), {"healthy": True})
        self.assertFalse(list(self.home.glob(".nykra-*.tmp")))

    def test_kernel_lock_prevents_duplicate_instance(self):
        self.home.mkdir(parents=True, exist_ok=True)
        with _single_instance(self.home / "runtime.lock"):
            with self.assertRaises(NykraError):
                with _single_instance(self.home / "runtime.lock"):
                    pass


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nykra-installer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "Nykra"
        self.startup = self.root / "Startup"
        self.source = Path(__file__).resolve().parents[1] / "nykra"

    def test_install_idempotent_update_and_uninstall(self):
        first = install_user(self.home, startup=self.startup, source=self.source)
        self.assertTrue(first["installed"])
        self.assertTrue(first["autostart_registered"])
        self.assertTrue(first["runtime_ready"])
        self.assertFalse(first["runtime"]["healthy"])
        script = (self.startup / AUTOSTART_FILENAME).read_bytes()
        self.assertIn(b"NYKRA-MANAGED-AUTOSTART", script)
        data = self.home / "keep-user-history.txt"
        data.write_text("keep", encoding="utf-8")
        second = install_user(self.home, startup=self.startup, source=self.source)
        self.assertEqual(second["version"], first["version"])
        self.assertEqual((self.startup / AUTOSTART_FILENAME).read_bytes(), script)
        removed = uninstall_user(self.home, startup=self.startup)
        self.assertTrue(removed["uninstalled"])
        self.assertTrue(removed["history_preserved"])
        self.assertEqual(data.read_text(), "keep")
        self.assertFalse((self.startup / AUTOSTART_FILENAME).exists())
        self.assertFalse((self.home / "runtime").exists())
        self.assertTrue(uninstall_user(self.home, startup=self.startup)["already_absent"])

    def test_unmanaged_startup_entry_refused(self):
        self.startup.mkdir()
        (self.startup / AUTOSTART_FILENAME).write_text("someone else's script", encoding="utf-8")
        with self.assertRaises(NykraError):
            install_user(self.home, startup=self.startup, source=self.source)
        self.assertEqual((self.startup / AUTOSTART_FILENAME).read_text(), "someone else's script")

    def test_modified_owned_startup_not_deleted(self):
        install_user(self.home, startup=self.startup, source=self.source)
        (self.startup / AUTOSTART_FILENAME).write_text("unexpected replacement", encoding="utf-8")
        with self.assertRaises(NykraError):
            uninstall_user(self.home, startup=self.startup)
        self.assertTrue((self.home / "installation.json").exists())


if __name__ == "__main__":
    unittest.main()
