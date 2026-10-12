"""v37 evaluator-owned hidden checks for previously-unused youtube-dl #32.

Frozen before any v37 model completion. Never disclose to either provider arm.
"""
import json
import unittest

from youtube_dl.utils import strip_jsonp
from youtube_dl.extractor.npo import NPOIE


class FrozenNpoJsonpChecks(unittest.TestCase):
    def test_metadata_comment_tail(self):
        payload='parseMetadata({"STATUS":"OK"})\n\n\n//epc'
        self.assertEqual(json.loads(strip_jsonp(payload)),{"STATUS":"OK"})

    def test_other_callback_and_comment(self):
        payload='cb_42({"a":[1,2],"x":true});\n// stale'
        self.assertEqual(json.loads(strip_jsonp(payload)),{"a":[1,2],"x":True})

    def test_basic_jsonp_compatibility(self):
        self.assertEqual(json.loads(strip_jsonp('cb({"x":3});')),{"x":3})

    def test_nested_array(self):
        self.assertEqual(json.loads(strip_jsonp('parseMetadata([1,{"k":5}])\n//epc')),
                         [1,{"k":5}])

    def test_npo_extractor_uses_jsonp_parser_with_comment(self):
        extractor=NPOIE(None)
        observed=[]
        def fake_download(url,video_id,*args,**kwargs):
            if not url.startswith("http://e.omroep.nl/metadata/aflevering/"):
                self.fail("Unexpected external request attempted")
            transform=kwargs.get("transform_source")
            if not callable(transform):
                self.fail("NPO metadata callback does not have a parser")
            observed.append(json.loads(transform('parseMetadata({"pubopties":[]})\n\n//epc')))
            raise StopIteration("public fixture stops immediately before network use")
        extractor._download_json=fake_download
        with self.assertRaises(StopIteration):
            extractor._get_info("offline-fixture")
        self.assertEqual(observed,[{"pubopties":[]}])


if __name__=="__main__":
    unittest.main()
