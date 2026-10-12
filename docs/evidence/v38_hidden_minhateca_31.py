"""Evaluator-owned Bug #31 regression checks, frozen before any model requests."""
import unittest
from youtube_dl.utils import parse_duration
from youtube_dl.extractor.minhateca import MinhatecaIE


class MinhatecaDurationHidden(unittest.TestCase):
    def test_mins_only(self):
        self.assertEqual(parse_duration("3 minutes"),180)
        self.assertEqual(parse_duration("1.5 mins"),90)
    def test_hours_only(self):
        self.assertEqual(parse_duration("1 hours"),3600)
        self.assertEqual(parse_duration("2.5 hours"),9000)
    def test_legacy_times(self):
        self.assertEqual(parse_duration("3h11m53s"),11513)
        self.assertEqual(parse_duration("01:02:03.05"),3723.05)
        self.assertEqual(parse_duration("5 s"),5)
    def test_invalid_and_none(self):
        self.assertIsNone(parse_duration("not a duration"))
        self.assertIsNone(parse_duration(None))
    def test_extractor_uses_shared_parser_for_text_units(self):
        import inspect
        source=inspect.getsource(MinhatecaIE._real_extract)
        self.assertIn("parse_duration(",source)
        self.assertNotIn("duration = int_or_none(",source)


if __name__=="__main__":
    unittest.main()
