"""Immutable withheld behavior suites for v0.21; never emit in public prompt."""
HIDDEN_TEST_MODULES={
 "youtube-dl-24":r"""
import unittest
from youtube_dl.utils import _match_one
class Hidden(unittest.TestCase):
 def test_numeric_string_compares_as_string(self):
  self.assertTrue(_match_one('id=12', {'id':'12'}))
  self.assertFalse(_match_one('id=12', {'id':'13'}))
 def test_numeric_value_remains_numeric(self):
  self.assertTrue(_match_one('id=12', {'id':12}))
""",
 "youtube-dl-25":r"""
import json,unittest
from youtube_dl.utils import js_to_json
class Hidden(unittest.TestCase):
 def test_hex_value(self):
  self.assertEqual(json.loads(js_to_json('{v:0x10}'))['v'],16)
 def test_octal_value(self):
  self.assertEqual(json.loads(js_to_json('{v:007}'))['v'],7)
 def test_decimal_unchanged(self):
  self.assertEqual(json.loads(js_to_json('{v:19}'))['v'],19)
""",
 "youtube-dl-27":r"""
import unittest
from youtube_dl.utils import parse_dfxp_time_expr
class Hidden(unittest.TestCase):
 def test_colon_fraction(self):
  self.assertAlmostEqual(parse_dfxp_time_expr('01:02:03:25'),3723.25)
 def test_dot_fraction(self):
  self.assertAlmostEqual(parse_dfxp_time_expr('01:02:03.25'),3723.25)
 def test_normal_clock(self):
  self.assertEqual(parse_dfxp_time_expr('00:00:05'),5)
""",
 "youtube-dl-28":r"""
import unittest
from youtube_dl.utils import _htmlentity_transform
class Hidden(unittest.TestCase):
 def test_out_of_unicode_range(self):
  self.assertEqual(_htmlentity_transform('#999999999999'), '&#999999999999;')
 def test_valid_numeric(self):
  self.assertEqual(_htmlentity_transform('#65'),'A')
 def test_invalid_name_preserved(self):
  self.assertEqual(_htmlentity_transform('not_an_entity'),'&not_an_entity;')
""",
 "youtube-dl-29":r"""
import unittest
from youtube_dl.utils import unified_strdate
class Hidden(unittest.TestCase):
 def test_unknown_date_returns_none(self):
  self.assertIsNone(unified_strdate('not a recognizable date'))
 def test_known_date_string(self):
  self.assertEqual(unified_strdate('2014-01-25'),'20140125')
 def test_none(self):
  self.assertIsNone(unified_strdate(None))
""",
 "youtube-dl-43":r"""
import unittest
from youtube_dl.utils import url_basename
class Hidden(unittest.TestCase):
 def test_multilevel_path(self):
  self.assertEqual(url_basename('https://example.org/a/b/c.mp4'),'c.mp4')
 def test_multilevel_with_query(self):
  self.assertEqual(url_basename('http://example.org/a/b/c.mp4?x=1'),'c.mp4')
 def test_no_path(self):
  self.assertEqual(url_basename('https://example.org/'),'')
""",
}
