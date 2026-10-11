"""Evaluator-owned withheld v0.20 behavior cases, SHA256 locked before inference."""
HIDDEN_TEST_MODULES = {
    "youtube-dl-3": r"""
import unittest
from youtube_dl.utils import unescapeHTML
class Hidden(unittest.TestCase):
    def test_bad_prefix_then_named(self):
        self.assertEqual(unescapeHTML('prefix &a&quot; suffix'), 'prefix &a" suffix')
    def test_two_bad_prefixes(self):
        self.assertEqual(unescapeHTML('&a&quot;|&b&amp;'), '&a"|&b&')
    def test_numeric_and_html5(self):
        self.assertEqual(unescapeHTML('&#47; and &apos;'), "/ and '")
""",
    "youtube-dl-5": r"""
import unittest
from youtube_dl.utils import unified_timestamp
from datetime import datetime, timezone
class Hidden(unittest.TestCase):
    def test_rfc_2822_fallback(self):
        self.assertEqual(unified_timestamp('Fri, 21 Nov 1997 09:55:06 -0600'),
                         int(datetime(1997,11,21,15,55,6,tzinfo=timezone.utc).timestamp()))
    def test_relative_pm(self):
        self.assertEqual(unified_timestamp('May 16, 2016 11:15 PM'),
                         int(datetime(2016,5,16,23,15,tzinfo=timezone.utc).timestamp()))
    def test_invalid_returns_none(self):
        self.assertIsNone(unified_timestamp('utter nonsense date'))
""",
    "youtube-dl-23": r"""
import json
import unittest
from youtube_dl.utils import js_to_json
class Hidden(unittest.TestCase):
    def test_inline_comment(self):
        self.assertEqual(json.loads(js_to_json('{alpha:1, // comment\n beta:2}')),
                         {'alpha': 1, 'beta': 2})
    def test_comment_without_slash_stripping_value(self):
        self.assertEqual(json.loads(js_to_json('{url:"https://example.org/a", // trailing\n ready:true}')),
                         {'url':'https://example.org/a','ready':True})
    def test_block_comment_still_works(self):
        self.assertEqual(json.loads(js_to_json('{a:1, /* block */ b:2}')),
                         {'a':1,'b':2})
""",
    "tqdm-1": r"""
import unittest
from tqdm.contrib import tenumerate
class FakeProgress:
    def __init__(self, iterable, **kwargs):
        self.data=iterable
        self.options=kwargs
    def __iter__(self):
        return iter(self.data)
class Hidden(unittest.TestCase):
    def test_custom_progress_nonzero(self):
        self.assertEqual(list(tenumerate(['a','b'],start=7,tqdm_class=FakeProgress)),
                         [(7,'a'),(8,'b')])
    def test_zero_offset_and_keyword_kwargs(self):
        self.assertEqual(list(tenumerate(['a'],start=0,tqdm_class=FakeProgress)),
                         [(0,'a')])
    def test_generator_iterable(self):
        self.assertEqual(list(tenumerate((i for i in range(2)),start=-2,tqdm_class=FakeProgress)),
                         [(-2,0),(-1,1)])
""",
}
