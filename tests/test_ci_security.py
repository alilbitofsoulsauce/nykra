"""Reject accidentally broad CI tokens, persisted credentials and stale action runtimes."""
from pathlib import Path
import re
import unittest

CI = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


class CISecurityTests(unittest.TestCase):
    def test_workflow_has_explicit_read_only_token(self):
        text = CI.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^permissions:\s*\n  contents: read$")
        self.assertNotRegex(text, r"(?m)^  (?:pull_request_target|workflow_run):")
        self.assertNotRegex(text, r"(?m)^\s+(?:actions|checks|contents|deployments|id-token|packages): write$")

    def test_every_checkout_drops_persisted_credentials(self):
        text = CI.read_text(encoding="utf-8")
        checkouts = re.findall(
            r"(?m)^\s+- uses: actions/checkout@([0-9a-f]{40}) # v7\s*\n"
            r"\s+with:\s*\n\s+persist-credentials: (\w+)\s*$", text)
        self.assertEqual(checkouts, [
            ("3d3c42e5aac5ba805825da76410c181273ba90b1", "false"),
            ("3d3c42e5aac5ba805825da76410c181273ba90b1", "false")])
        self.assertEqual(len(re.findall(
            r"(?m)^\s+- uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7$",
            text)), 2)
        self.assertIn("os: [ubuntu-24.04, windows-latest, macos-latest]", text)
        self.assertIn("runs-on: ubuntu-24.04", text)


if __name__ == "__main__":
    unittest.main()
