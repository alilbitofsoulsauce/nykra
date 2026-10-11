"""Frozen, evaluator-only hidden behavior probes for the v0.18 pilot.

The agent's read-only, tool-free model prompt contains neither this source
nor the expected results. Keep this file SHA256-pinned in the protocol and do
not alter it once any model candidate has been generated.
"""
HIDDEN_TEST_MODULES = {
    "youtube-dl-17": r"""
import unittest
from youtube_dl import utils as u
class Hidden(unittest.TestCase):
    def test_absent_and_bool_flags(self):
        self.assertEqual(u.cli_bool_option({}, '--feature', 'enabled'), [])
        self.assertEqual(u.cli_bool_option({'enabled': None}, '--feature', 'enabled'), [])
        self.assertEqual(u.cli_bool_option({'enabled': True}, '--feature', 'enabled'), ['--feature','true'])
        self.assertEqual(u.cli_bool_option({'enabled': False}, '--feature', 'enabled', separator='='), ['--feature=false'])
    def test_separators_and_values(self):
        self.assertEqual(u.cli_bool_option({'x': True}, '-x', 'x', true_value='YES', separator='='), ['-x=YES'])
        self.assertEqual(u.cli_bool_option({'x': False}, '-x', 'x', false_value='NO'), ['-x','NO'])
        with self.assertRaises(AssertionError):
            u.cli_bool_option({'x':'not-a-bool'}, '-x','x')
""",
    "youtube-dl-20": r"""
import unittest
from youtube_dl import utils as u
class Hidden(unittest.TestCase):
    def test_other_unvalued_attributes(self):
        html = '<div disabled data-id="q">FIRST</div>'
        self.assertEqual(u.get_elements_by_attribute('data-id','q',html), ['FIRST'])
    def test_unvalued_attribute_after_target(self):
        html = '<section data-id="q" checked>SECOND</section>'
        self.assertEqual(u.get_elements_by_attribute('data-id','q',html), ['SECOND'])
    def test_ordinary_value_still_works(self):
        html = '<span data-id="q">THIRD</span>'
        self.assertEqual(u.get_elements_by_attribute('data-id','q',html), ['THIRD'])
""",
    "youtube-dl-21": r"""
import unittest
from youtube_dl import utils as u
class Hidden(unittest.TestCase):
    def test_bytes_absolute_path(self):
        self.assertEqual(u.urljoin(b'https://example.org/root/',b'next'), 'https://example.org/root/next')
    def test_bytes_relative_path(self):
        self.assertEqual(u.urljoin('https://example.org/root/',b'../item'), 'https://example.org/item')
    def test_bytes_base(self):
        self.assertEqual(u.urljoin(b'https://example.org/root/', 'next'), 'https://example.org/root/next')
    def test_invalid_path(self):
        self.assertIsNone(u.urljoin('https://example.org/root/', b''))
""",
    "PySnooper-3": r"""
import unittest
import tempfile
from pathlib import Path
from pysnooper.pysnooper import get_write_function
class Hidden(unittest.TestCase):
    def test_append_to_named_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'trace.txt'
            writer = get_write_function(str(p))
            writer('alpha\n')
            writer('beta\n')
            self.assertEqual(p.read_text(), 'alpha\nbeta\n')
    def test_append_to_pathlike(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'trace.log'
            writer = get_write_function(p)
            writer('ok')
            self.assertEqual(p.read_text(), 'ok')
""",
}
