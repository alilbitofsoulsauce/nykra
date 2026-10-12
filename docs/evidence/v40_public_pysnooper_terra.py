"""v40 public regression for PySnooper unicode compatibility, frozen before Terra generation."""
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pysnooper import pycompat
from pysnooper.tracer import FileWriter,get_source_from_frame,source_cache


class PublicCompatibility(unittest.TestCase):
    def test_source_is_utf8_without_explicit_header(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"trace_me.py"
            p.write_text("def frame():\n    import sys\n    return sys._getframe()\n# 失败\n",encoding="utf-8")
            ns={"__name__":"v40_public_unicode","__file__":str(p)}
            exec(compile(p.read_text(encoding="utf-8"),str(p),"exec"),ns)
            source_cache.clear()
            self.assertEqual(get_source_from_frame(ns["frame"]())[3],"# 失败")

    def test_utf8_output_is_explicit(self):
        original=builtins.open
        seen=[]
        def wrapper(*args,**kwargs):
            seen.append(kwargs.get("encoding"))
            return original(*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"events.log"
            with patch("builtins.open",wrapper):
                FileWriter(str(p),True).write("彩色\n")
            self.assertEqual(seen,["utf-8"])
            self.assertEqual(p.read_bytes(),"彩色\n".encode("utf-8"))

    def test_compatibility_flags_coherent(self):
        self.assertEqual(pycompat.PY2,not pycompat.PY3)


if __name__=="__main__":
    unittest.main()
