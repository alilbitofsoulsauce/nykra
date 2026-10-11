"""Exercise actual model-candidate ancestry decisions on disposable Git code."""
import tempfile
import unittest
from pathlib import Path

from nykra.repo_policy_runner import explore_repo, run_trusted_fixture
from nykra.repository_repair_trial import extract_function, prepare_repository, protocol


class RepositoryPolicyTests(unittest.TestCase):
    def task(self):
        return next(x for x in protocol()["tasks"] if x["id"] == "pvalue-tail")

    def test_adaptive_stagnation_branches_and_then_solves(self):
        task = self.task()
        with tempfile.TemporaryDirectory(prefix="nykra-policy-test-") as directory:
            root = Path(directory)
            broken = prepare_repository(task, root)
            good = prepare_repository(task, root, mutate=False)
            bad_source = extract_function(
                (broken / task["file"]).read_text(encoding="utf-8"), task["function"]
            )
            good_source = extract_function(
                (good / task["file"]).read_text(encoding="utf-8"), task["function"]
            )
            initial_contents = (broken / task["file"]).read_bytes()
            requests = []
            answers = iter([bad_source, bad_source, bad_source, good_source])
            def propose(prompt, timeout):
                requests.append(prompt)
                return {"status": "ok", "source": next(answers),
                        "seconds": 0.1, "tokens": 10}
            result = explore_repo(task, broken, policy="adaptive", budget=4,
                                  proposer=propose)
            self.assertEqual(result["evaluations_used"], 4)
            self.assertTrue(result["heldout_success"])
            self.assertEqual(result["heldout_passed"], 26)
            self.assertEqual(result["best_attempt_id"], "attempt-4")
            self.assertEqual(
                [a["kind"] for a in result["candidate_attempts"]],
                ["new_root", "revise", "revise", "new_root"],
            )
            self.assertEqual(
                [a["parent_attempt_id"] for a in result["candidate_attempts"]],
                [None, "attempt-1", "attempt-2", None],
            )
            self.assertIn("EXPLORATION BRANCH", requests[-1])
            self.assertEqual((broken / task["file"]).read_bytes(), initial_contents)

    def test_breadth_creates_second_root_before_revisions(self):
        task = self.task()
        with tempfile.TemporaryDirectory(prefix="nykra-policy-breadth-") as directory:
            repo = prepare_repository(task, Path(directory))
            bad_source = extract_function((repo / task["file"]).read_text(), task["function"])
            calls = []
            def propose(prompt, timeout):
                calls.append(prompt)
                return {"status": "ok", "source": bad_source,
                        "seconds": .1, "tokens": 1}
            outcome = explore_repo(task, repo, policy="breadth", budget=3,
                                   proposer=propose)
            self.assertEqual(outcome["evaluations_used"], 3)
            self.assertEqual(
                [x["kind"] for x in outcome["candidate_attempts"]],
                ["new_root", "new_root", "revise"],
            )
            self.assertEqual(outcome["candidate_attempts"][-1]["parent_attempt_id"],
                             "attempt-1")
            self.assertEqual(outcome["heldout_success"], False)

    def test_model_calls_and_external_tasks_require_authorization(self):
        with self.assertRaises(ValueError):
            run_trusted_fixture("pvalue-tail", approval=False)
        with self.assertRaises(ValueError):
            run_trusted_fixture("unlisted-external-github-issue", approval=True)


if __name__ == "__main__":
    unittest.main()
