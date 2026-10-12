"""Release scanner must inspect staged/tracked files and optional pending inputs."""
import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/check_release_inputs.py"
spec=importlib.util.spec_from_file_location("nykra_release_inputs",SCRIPT)
scanner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class ReleaseInputTests(unittest.TestCase):
    def test_untracked_optin_does_not_mistake_pending_files_for_required_tracked(self):
        with tempfile.TemporaryDirectory(prefix="nykra-release-scan-") as temp:
            repo=Path(temp)
            subprocess.run(["git","init","-q",str(repo)],check=True)
            (repo/"README.md").write_text("Safe public project\n",encoding="utf-8")
            subprocess.run(["git","-C",str(repo),"add","README.md"],check=True)
            (repo/"new.py").write_text("access = 'sk-' + 'x'*40\n",encoding="utf-8")
            with patch.object(scanner,"ROOT",repo),patch.object(scanner,"REQUIRED",{"README.md"}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(scanner.main([]),0)
                # Use a concatenation in fixture to avoid real credential literals
                # in release sources; write the test marker into the isolated repo.
                (repo/"new.py").write_text("sk-"+"x"*40,encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(scanner.main(["--include-untracked"]),1)
                self.assertIn("new.py",err.getvalue())
                (repo/"needed.md").write_text("pending documentation",encoding="utf-8")
                with patch.object(scanner,"REQUIRED",{"README.md","needed.md"}):
                    with contextlib.redirect_stderr(io.StringIO()) as err:
                        self.assertEqual(scanner.main(["--include-untracked"]),1)
                    self.assertIn("required OSS source not tracked: needed.md",err.getvalue())


if __name__=="__main__":
    unittest.main()
