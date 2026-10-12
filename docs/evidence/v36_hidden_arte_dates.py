"""Evaluator-owned checks for upstream BugsInPy youtube-dl #35.

Written/frozen before any v36 model proposal. Never shown in coding prompt.
"""
import unittest

from youtube_dl.utils import unified_strdate
from youtube_dl.extractor.arte import ArteTVPlus7IE


class HiddenArteDateChecks(unittest.TestCase):
    def _extract(self, player):
        instance = ArteTVPlus7IE(None)
        instance._download_json = lambda json_url, video_id: {
            "videoJsonPlayer": {
                "VID": "offline-arte-example",
                "VTI": "Mock German broadcast",
                "VSR": {"a": {"quality": "HQ", "versionCode": None,
                              "mediaType": "http",
                              "url": "https://example.invalid/video.mp4"}},
                **player
            }
        }
        return instance._extract_from_json_url("https://example.invalid/api", "offline", "de")

    def test_arte_shooting_date_overrides_vda(self):
        data = self._extract({
            "shootingDate": "28/01/2014 21:00:00 +0100",
            "VDA": "12/01/2014 12:00:00 +0100"
        })
        self.assertEqual(data["upload_date"], "20140128")
        self.assertEqual(data["id"], "offline-arte-example")

    def test_arte_falls_back_if_shooting_date_is_missing(self):
        data = self._extract({"VDA": "2014-02-02 00:00:00"})
        self.assertEqual(data["upload_date"], "20140202")

    def test_arte_falls_back_if_shooting_date_is_empty(self):
        data = self._extract({
            "shootingDate": "",
            "VDA": "2014-05-06 09:00:00",
        })
        self.assertEqual(data["upload_date"], "20140506")

    def test_legacy_date_formats_are_preserved(self):
        self.assertEqual(unified_strdate("2013-03-04"), "20130304")
        self.assertEqual(unified_strdate("December 21, 2010"), "20101221")

    def test_day_first_datetime_with_utc_offset(self):
        self.assertEqual(unified_strdate("28/01/2014 21:00:00 +0100"), "20140128")


if __name__ == "__main__":
    unittest.main()
