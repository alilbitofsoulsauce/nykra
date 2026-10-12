"""Evaluator-only PySnooper #1 checks, independently frozen before model inference."""
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pysnooper import pycompat
from pysnooper.tracer import FileWriter,get_source_from_frame,source_cache


class UnicodeTraceHidden(unittest.TestCase):
    def test_py2_flag_matches_inverse_of_py3(self):
        self.assertIs(pycompat.PY2,not pycompat.PY3)

    def test_utf8_source_multibyte_characters_preserved(self):
        with tempfile.TemporaryDirectory(prefix="nykra-hidden-pysnooper-") as folder:
            file=Path(folder)/"source.py"
            file.write_text("def f():\n    import sys\n    return sys._getframe()\n# 中文 café\n",encoding="utf-8")
            scope={"__name__":"nykra_hidden_unicode_39","__file__":str(file)}
            exec(compile(file.read_text(encoding="utf-8"),str(file),"exec"),scope)
            source_cache.clear()
            self.assertEqual(get_source_from_frame(scope["f"]())[3],"# 中文 café")

    def test_logwriter_explicit_utf8(self):
        real_open=builtins.open
        observed=[]
        def tracking_open(*args,**kwargs):
            observed.append(kwargs.get("encoding"))
            return real_open(*args,**kwargs)
        with tempfile.TemporaryDirectory(prefix="nykra-hidden-pysnooper-") as folder:
            file=Path(folder)/"trace.log"
            with patch("builtins.open",tracking_open):
                FileWriter(str(file),True).write("失败 — café\n")
            self.assertEqual(file.read_bytes(),"失败 — café\n".encode("utf-8"))
            self.assertEqual(observed,["utf-8"])


if __name__=="__main__":
    unittest.main()
