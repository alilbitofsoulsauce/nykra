"""Live ChatGPT/Rel.AI-style proposal callback with public-result reuse."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra import agent_workflow as wf, v23_paired
from nykra.v21_grader import function_at,manifest


class ConnectedProviderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        mock=patch.object(wf,"SESSIONS",Path(temp.name)/"sessions")
        mock.start()
        self.addCleanup(mock.stop)
        t=next(x for x in manifest()[0]["tasks"] if x["id"]=="youtube-dl-43")
        self.correct=function_at(t,t["fixed_commit"])

    def test_provider_required_no_codex_auto_call(self):
        with self.assertRaisesRegex(ValueError,"approval"):
            v23_paired.run_pair("youtube-dl-43",lambda _:self.correct)
        with self.assertRaisesRegex(ValueError,"callback"):
            v23_paired.run_pair("youtube-dl-43",None,approve=True)

    def test_early_shared_success_requires_one_public_docker_and_two_hidden(self):
        events=[]
        def grade(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"ok","passed":True}
        proposals=[]
        def propose(prompt):
            proposals.append(prompt)
            return self.correct
        with patch.object(wf,"grade",side_effect=grade):
            report=v23_paired.run_pair("youtube-dl-43",propose,budget=4,approve=True)
        self.assertEqual(len(proposals),1)
        self.assertEqual(events,["public","hidden","hidden"])
        self.assertEqual(report["requested_candidate_instances"],2)
        self.assertEqual(report["real_public_docker_runs"],1)
        self.assertEqual(report["real_git_apply_calls"],1)
        self.assertEqual(report["verified_public_reuse"],1)
        self.assertTrue(report["final"]["depth"]["full_success"])
        self.assertTrue(report["final"]["adaptive"]["full_success"])

    def test_genuine_fork_reuses_only_three_identical_prefixes(self):
        events=[]
        def grader(task,*,mode,candidate=None):
            events.append(mode)
            return {"status":"test_failed","passed":False}
        with patch.object(wf,"grade",side_effect=grader):
            report=v23_paired.run_pair("youtube-dl-43",lambda _:self.correct,budget=4,approve=True)
        self.assertEqual(report["policy_divergence"]["depth"]["kind"],"revise")
        self.assertEqual(report["policy_divergence"]["adaptive"]["kind"],"new_root")
        self.assertEqual(report["model_proposal_invocations"],5)
        self.assertEqual(len(events),5)  # no hidden without public success
        self.assertEqual(report["real_public_docker_runs"],5)
        self.assertEqual(report["real_git_apply_calls"],5)
        self.assertEqual(report["verified_public_reuse"],3)
        self.assertEqual(report["requested_candidate_instances"],8)
        self.assertFalse(report["final"]["depth"]["full_success"])
        self.assertFalse(report["final"]["adaptive"]["full_success"])


if __name__=="__main__":
    unittest.main()
