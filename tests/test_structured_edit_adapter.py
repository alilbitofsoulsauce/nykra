"""Deterministic and secure structured edits to real Git patches."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from nykra.structured_edit_adapter import exact_edits_to_diff
from nykra.transactional_patch import PatchRejected

A="engine/calc.py"
B="engine/routes.py"
ORIGINAL={A:b"def total(a, b):\n    return a-b\n",
          B:b"from engine.calc import total\n\ndef invoice(a,b):\n    return str(total(a,b)-1)\n"}


def proposal(*rows):
    return json.dumps({"edits":list(rows)})


class StructuredEditTests(unittest.TestCase):
    def generate(self,raw):
        return exact_edits_to_diff(raw,originals=ORIGINAL,allowed_paths=[A,B])

    def test_two_file_git_diff_applies_exactly(self):
        raw=proposal({"path":A,"old":"return a-b","new":"return a+b"},
                     {"path":B,"old":"return str(total(a,b)-1)",
                      "new":"return str(total(a,b))"})
        diff,meta=self.generate(raw)
        self.assertEqual(meta["files_changed"],[A,B])
        self.assertEqual(len(meta["edits"]),2)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for name,content in ORIGINAL.items():
                file=folder/name;file.parent.mkdir(parents=True,exist_ok=True)
                file.write_bytes(content)
            subprocess.run(["git","init","-q"],cwd=folder,check=True)
            path=folder/"patch.diff"
            path.write_text(diff,encoding="utf-8",newline="\n")
            trial=subprocess.run(["git","apply","--check",str(path)],
                                 cwd=folder,capture_output=True)
            self.assertEqual(trial.returncode,0,trial.stderr)
            subprocess.run(["git","apply",str(path)],cwd=folder,check=True)
            self.assertIn("return a+b",(folder/A).read_text())
            self.assertIn("return str(total(a,b))",(folder/B).read_text())
        self.assertIn(b"return a-b",ORIGINAL[A])

    def test_allowlist_rejects_tests_and_path_traversal(self):
        for name in ("tests/test_invoice.py","../secret.py","engine\\calc.py"):
            with self.subTest(name=name):
                with self.assertRaises(PatchRejected):
                    self.generate(proposal({"path":name,
                                            "old":"return a-b","new":"return a+b"}))

    def test_ambiguous_and_overlapping_spans_fail_closed(self):
        files={A:b"x=5\nx=5\n",B:ORIGINAL[B]}
        with self.assertRaisesRegex(PatchRejected,"not unique"):
            exact_edits_to_diff(proposal({"path":A,"old":"x=5","new":"x=6"}),
                                originals=files,allowed_paths=[A,B])
        with self.assertRaisesRegex(PatchRejected,"overlapping"):
            self.generate(proposal(
                {"path":A,"old":"return a-b","new":"return a+b"},
                {"path":A,"old":"a-b","new":"a+b"}))

    def test_bad_schema_and_unsafe_content_rejected(self):
        invalid=[
          "not json",json.dumps({"edits":[]}),
          json.dumps({"edits":[{"path":A,"old":"a-b","new":"a+b","extra":0}]}),
          proposal({"path":A,"old":"a-b","new":"a-b"}),
          proposal({"path":A,"old":"a-b","new":"\x00"}),
          proposal({"path":A,"old":"a-b","new":"a\r+b"}),
          proposal({"path":A,"old":"not present","new":"new"})
        ]
        for sample in invalid:
            with self.subTest(sample=sample[:35]):
                with self.assertRaises(PatchRejected):self.generate(sample)

    def test_malformed_unicode_fails_closed(self):
        malformed=json.dumps({"edits":[{"path":A,"old":"return a-b",
                                         "new":"return a+\ud800"}]})
        with self.assertRaisesRegex(PatchRejected,"valid UTF-8"):
            self.generate(malformed)
        with self.assertRaisesRegex(PatchRejected,"valid UTF-8"):
            self.generate("\ud800")

    def test_multiple_disjoint_edits_are_deterministic(self):
        text=proposal({"path":A,"old":"def total","new":"def plus"},
                      {"path":A,"old":"return a-b","new":"return a+b"})
        first,meta=self.generate(text)
        second,_=self.generate(text)
        self.assertEqual(first,second)
        self.assertEqual(meta["files_changed"],[A])

    def test_long_response_rejected(self):
        with self.assertRaises(PatchRejected):self.generate("a"*60001)


if __name__=="__main__":
    unittest.main()
