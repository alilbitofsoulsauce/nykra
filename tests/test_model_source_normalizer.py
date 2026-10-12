"""Tests for deterministic safe stdlib import preamble source normalizer."""
import ast
import unittest

from nykra.model_source_normalizer import normalize_function_imports
from nykra.repair_feedback import validate_replacement

ORIGINAL = "def url_basename(url):\n    return url\n"


class ModelSourceNormalizationTests(unittest.TestCase):
    def test_standalone_function_unchanged(self):
        code = "def url_basename(url):\n    return str(url)\n"
        x = normalize_function_imports(code, name="url_basename", original=ORIGINAL)
        self.assertEqual(x["status"], "unchanged")
        self.assertEqual(x["source"], code)
        self.assertEqual(x["import_statements_moved"], 0)

    def test_safe_import_preamble_moved_without_changing_logic(self):
        code = ("import re\nfrom urllib.parse import urlparse\n\n"
                "def url_basename(url):\n"
                "    return re.sub('x','y',urlparse(url).path)\n")
        x = normalize_function_imports(code, name="url_basename", original=ORIGINAL)
        self.assertEqual(x["status"], "normalized_stdlib_imports")
        self.assertEqual(x["import_statements_moved"], 2)
        self.assertIsNone(validate_replacement(x["source"], name="url_basename",
                                               original=ORIGINAL))
        ast_before = ast.parse(code)
        ast_after = ast.parse(x["source"])
        function_before = ast_before.body[-1]
        function_after = ast_after.body[0]
        self.assertEqual(
            [ast.dump(x, include_attributes=False) for x in function_before.body],
            [ast.dump(x, include_attributes=False) for x in function_after.body[2:]],
        )

    def test_any_non_import_top_level_code_is_rejected(self):
        code = "print('side effect')\ndef url_basename(url):\n    return url\n"
        self.assertEqual(normalize_function_imports(
            code, name="url_basename", original=ORIGINAL)["status"],
            "unrecognized_source")

    def test_disallowed_import_blocks_transform(self):
        for prelude in ("import subprocess", "from ctypes import CDLL",
                        "from os import system", "import numpy",
                        "from .utils import x", "from re import *"):
            with self.subTest(prelude=prelude):
                result = normalize_function_imports(
                    prelude+"\ndef url_basename(url):\n    return url\n",
                    name="url_basename", original=ORIGINAL)
                self.assertEqual(result["status"], "unrecognized_source")

    def test_docstring_preserved_when_imports_move_inside(self):
        source = ('import re\n'
                  'def url_basename(url):\n'
                  '    """Keep this docstring"""\n'
                  '    return re.sub("a", "b", url)\n')
        result = normalize_function_imports(
            source, name="url_basename", original=ORIGINAL)
        self.assertEqual(result["status"], "normalized_stdlib_imports")
        function = ast.parse(result["source"]).body[0]
        self.assertEqual(ast.get_docstring(function), "Keep this docstring")
        self.assertIsInstance(function.body[1], ast.Import)

    def test_signature_changes_remain_invalid(self):
        candidate = "import re\ndef url_basename(url, extra=1):\n    return url\n"
        result = normalize_function_imports(
            candidate, name="url_basename", original=ORIGINAL)
        self.assertEqual(result["status"], "unrecognized_source")

    def test_bad_or_multiple_functions_are_rejected(self):
        for raw in ("def url_basename(url): invalid syntax ?",
                    "import re\ndef other(url):\n    return url\n",
                    "import re\ndef url_basename(url):\n    return url\n"
                    "def extra():\n    return False\n"):
            self.assertEqual(normalize_function_imports(
                raw, name="url_basename", original=ORIGINAL)["status"],
                "unrecognized_source")


if __name__ == "__main__":
    unittest.main()
