"""Evaluator-owned Bug #33 regression checks, frozen before any model requests."""
import unittest
from types import SimpleNamespace
from youtube_dl.utils import parse_iso8601
from youtube_dl.extractor.drtv import DRTVIE


class DRTVTimestampHidden(unittest.TestCase):
    def test_fractional_utc(self):
        self.assertEqual(parse_iso8601("2014-03-23T22:04:26.1234Z"),1395612266)
    def test_fractional_plus_timezone(self):
        self.assertEqual(parse_iso8601("2014-03-23T23:04:26.1234+0100"),1395612266)
    def test_fractional_minus_timezone(self):
        self.assertEqual(parse_iso8601("2014-03-23T17:04:26.1234-0500"),1395612266)
    def test_legacy_utc(self):
        self.assertEqual(parse_iso8601("2014-03-23T22:04:26Z"),1395612266)
    def test_extractor_keeps_timezone_and_fraction_semantics(self):
        instance=DRTVIE(None)
        instance._downloader=SimpleNamespace(params={})
        instance._download_json=lambda *args,**kwargs:{
            "Data":[{"Title":"Offline television","Description":"Fixture",
                     "CreatedTime":"2014-03-23T23:04:26.1234+0100",
                     "Assets":[]}]
        }
        instance._sort_formats=lambda formats:None
        instance.extract_subtitles=lambda *args,**kwargs:{}
        result=instance._real_extract(
            "http://www.dr.dk/tv/se/partiets-mand/partiets-mand-7-8")
        self.assertEqual(result["timestamp"],1395612266)
        self.assertEqual(result["id"],"partiets-mand-7-8")
        self.assertEqual(result["title"],"Offline television")


if __name__=="__main__":
    unittest.main()
