"""Ensure local release-candidate identifiers and provenance stay aligned."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from nykra import __version__
from nykra.ide import package_vsix

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_ARCHIVES={
    "docs/evidence/v37_original_structured_edit_adapter.py":
        "adac639e6aa7f473c33718651bf81d56c82d5393b18f812082ac7caf9fea9f87",
    "docs/evidence/v37_original_structured_edit_tests.py":
        "99bb2d05dd15de8e840c3039b0792233cbb72fedb1fe577a50be921c8f0d1c53",
}


class ReleaseCandidateTests(unittest.TestCase):
    def test_python_project_and_editor_versions_match(self):
        project=(ROOT/"pyproject.toml").read_text(encoding="utf-8")
        matched=re.search(r'(?m)^version = "([0-9]+\.[0-9]+\.[0-9]+)"$',project)
        self.assertIsNotNone(matched)
        extension=json.loads((ROOT/"nykra/ide_extension/package.json").read_text(encoding="utf-8"))
        self.assertEqual((__version__,matched.group(1),extension["version"]),
                         ("0.26.0",)*3)

    def test_versioned_extension_can_be_packaged(self):
        with tempfile.TemporaryDirectory(prefix="nykra-rc-vsix-") as temp:
            path=package_vsix(Path(temp)/"nykra-observer.vsix")
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(json.loads(archive.read("extension/package.json"))["version"],
                                 __version__)
                self.assertIn(__version__,archive.read("extension.vsixmanifest").decode("utf-8"))

    def test_pre_hardening_benchmark_snapshots_are_byte_preserved(self):
        for relative,digest in EXPECTED_ARCHIVES.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),digest)

    def test_unreleased_label_and_changelog_are_explicit(self):
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        changelog=(ROOT/"CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Unreleased v0.26.0 release candidate",readme)
        self.assertIn("0.26.0 — Release candidate prepared, not yet published",changelog)
        self.assertIn("do not establish a general coding success-rate increase",changelog)


if __name__=="__main__":
    unittest.main()
