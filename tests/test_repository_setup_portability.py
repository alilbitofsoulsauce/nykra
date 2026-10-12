"""Portable disposable repository setup must tolerate bounded Windows Git staging."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nykra.repository_repair_trial import prepare_repository, protocol


class RepositorySetupPortabilityTests(unittest.TestCase):
    def test_disposable_staging_has_bounded_windows_headroom(self):
        task = protocol()["tasks"][0]
        observed = []

        def fake_git(command, **kwargs):
            observed.append((tuple(command), kwargs["timeout"]))
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory(prefix="nykra-repo-setup-") as directory:
            with patch("nykra.repository_repair_trial.subprocess.run", side_effect=fake_git):
                checkout = prepare_repository(task, Path(directory))
            self.assertTrue(checkout.is_dir())

        self.assertEqual([command[:2] for command, _ in observed],
                         [("git", "init"), ("git", "add"), ("git", "-c")])
        self.assertEqual([timeout for _, timeout in observed], [12, 60, 12])


if __name__ == "__main__":
    unittest.main()
