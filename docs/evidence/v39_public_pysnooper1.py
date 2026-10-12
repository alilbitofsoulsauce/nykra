"""Public offline PySnooper #1 regression derived from original upstream Chinese-source case."""
import tempfile
import unittest
from pathlib import Path
from pysnooper.tracer import get_source_from_frame, source_cache


class UnicodeSourcePublic(unittest.TestCase):
    def test_utf8_source_without_coding_header(self):
        with tempfile.TemporaryDirectory(prefix="pysnooper-source-") as temp:
            path=Path(temp)/"example.py"
            path.write_text("def f():\n    import sys\n    return sys._getframe()\n# 失败\n",encoding="utf-8")
            space={"__name__":"test_pysnooper_unicode_39","__file__":str(path)}
            exec(compile(path.read_text(encoding="utf-8"),str(path),"exec"),space)
            source_cache.clear()
            lines=get_source_from_frame(space["f"]())
            self.assertEqual(lines[3],"# 失败")


if __name__=="__main__":
    unittest.main()
