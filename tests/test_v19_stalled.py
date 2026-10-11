"""Secondary v0.19 fork replay must be pre-hashed, conditional, and fail closed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nykra.v19_stalled_replay import manifest, recorded_prefix, replay
from nykra.v19_fork_trial import fork_actions, protocol


class StalledForkTests(unittest.TestCase):
    def test_deterministic_conditional_cohort_hashes(self):
        data, sha=manifest()
        self.assertEqual(len(sha),64)
        self.assertEqual(data["cohort_size"],3)
        self.assertEqual([x["task_id"] for x in data["selected"]],
                         ["youtube-dl-20","youtube-dl-21","PySnooper-3"])
        for row in data["selected"]:
            prefix,_=recorded_prefix(row["task_id"])
            self.assertEqual(len(prefix),3)
            self.assertEqual([x["public"]["status"] for x in prefix],
                             ["test_failed"]*3)
            forks=fork_actions(prefix,protocol()[0])
            self.assertEqual(forks["baseline"]["kind"],"revise")
            self.assertEqual(forks["nykra"]["kind"],"new_root")

    def test_explicit_approval_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"old.json"
            with self.assertRaises(ValueError):
                replay("youtube-dl-20",out)
            out.write_text("old")
            with self.assertRaisesRegex(ValueError,"overwrite"):
                replay("youtube-dl-20",out,approve=True)
            self.assertEqual(out.read_text(),"old")

    def test_revalidation_fails_before_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"result.json"
            def invalid_grade(task,*,mode,candidate=None):
                return {"status":"ok","passed":True}
            proposer_calls=[]
            def propose(prompt,seconds):
                proposer_calls.append(prompt)
                raise AssertionError("should not call model")
            with patch("nykra.v19_stalled_replay.grade",
                       side_effect=invalid_grade):
                r=replay("youtube-dl-20",out,approve=True,
                         proposer=propose)
            self.assertEqual(r["status"],"revalidation_excluded")
            self.assertFalse(proposer_calls)
            self.assertEqual(len(r["revalidation"]),1)

if __name__=="__main__":
    unittest.main()
