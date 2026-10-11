import json
import tempfile
import unittest
from pathlib import Path

from integrations.relai.host_integration import HostIntegrationError, apply, inspect, remove


class HostPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host = Path(self.tmp.name)
        (self.host / "src" / "tools").mkdir(parents=True)
        (self.host / "package.json").write_text(json.dumps({"name": "rel-ai-mcp"}), encoding="utf-8")
        self.entry = self.host / "src/tools/callTool.js"
        self.original = (
            b"import { buildToolActivityDetails } from '../taskObservability.js';\r\n"
            b"const foo = 1;\r\n"
            b"bindTaskHistoryActivityPersistence(onToolActivity, readConfig);\r\n"
            b"function doTheWork() { return foo; }\r\n"
        )
        self.entry.write_bytes(self.original)

    def test_apply_reapply_remove_exact_content(self):
        self.assertEqual(inspect(self.host)["state"], "compatible")
        self.assertTrue(apply(self.host)["changed"])
        current = self.entry.read_bytes()
        self.assertIn(b"attachRelaiBridge(onToolActivity)", current)
        self.assertIn(b"\r\n", current)
        self.assertFalse(apply(self.host)["changed"])
        self.assertTrue(remove(self.host)["changed"])
        self.assertEqual(self.entry.read_bytes(), self.original)
        self.assertFalse((self.host / "src/tools/nykraBridge.mjs").exists())
        self.assertFalse(remove(self.host)["changed"])

    def test_conflicting_host_edit_refuses_destructive_rollback(self):
        apply(self.host)
        self.entry.write_bytes(self.entry.read_bytes() + b"\n// other changes\n")
        with self.assertRaises(HostIntegrationError):
            remove(self.host)
        self.assertIn(b"other changes", self.entry.read_bytes())

    def test_unsupported_host_never_changed(self):
        self.entry.write_bytes(b"import './something-else.js';")
        with self.assertRaises(HostIntegrationError):
            apply(self.host)
        self.assertEqual(self.entry.read_bytes(), b"import './something-else.js';")


if __name__ == "__main__":
    unittest.main()
