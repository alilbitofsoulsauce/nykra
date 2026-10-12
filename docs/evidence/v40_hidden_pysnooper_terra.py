"""v40 evaluator-only posthoc source variants, frozen before Terra model calls."""
import builtins
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pysnooper import pycompat
from pysnooper.tracer import FileWriter,get_source_from_frame,source_cache


class HeldoutCompatibility(unittest.TestCase):
    def test_extra_multibyte_source_line_without_header(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"source.py"
            p.write_text("def frame():\n    import sys\n    return sys._getframe()\n# 日本語 🐈 café\n",encoding="utf-8")
            ns={"__name__":"v40_hidden_multibyte","__file__":str(p)}
            exec(compile(p.read_text(encoding="utf-8"),str(p),"exec"),ns)
            source_cache.clear()
            self.assertEqual(get_source_from_frame(ns["frame"]())[3],"# 日本語 🐈 café")

    def test_writer_utf8_append_after_first_write(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"trace.log"
            writer=FileWriter(str(p),True)
            writer.write("一行目\n")
            writer.write("第二行\n")
            self.assertEqual(p.read_bytes(),"一行目\n第二行\n".encode("utf-8"))

    def test_explicit_encoding_in_append_mode(self):
        original=builtins.open
        kwargs_seen=[]
        def spy(*args,**kwargs):
            kwargs_seen.append((args[1] if len(args)>1 else kwargs.get("mode"),
                                kwargs.get("encoding")))
            return original(*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            writer=FileWriter(str(Path(directory)/"trace.log"),True)
            with patch("builtins.open",spy):
                writer.write("こんにちは\n")
                writer.write("مرحبا\n")
        self.assertEqual(kwargs_seen,[("w","utf-8"),("a","utf-8")])
        self.assertIs(pycompat.PY2,not pycompat.PY3)


if __name__=="__main__":
    unittest.main()
