"""Prove v0.8 exploration policy changes actual agent execution order."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nykra.agent_host import (SubprocessSearchHost, evaluate_grid,
                               validate_grid, run_reference_benchmark)
from nykra.evaluation import EvaluatorResult
from nykra.prospective import ProspectiveExperiment
from nykra.store import HistoryStore, NykraError


TASK = {"width":4,"height":4,"start":[0,0],"goal":[3,3],
        "walls":[[1,1],[2,1]]}


class AgentHostTests(unittest.TestCase):
    def test_reference_agent_produces_runtime_proposals(self):
        request={"task": TASK, "path":[[0,0]]}
        worker=Path(__file__).resolve().parents[1]/"nykra"/"reference_agent.py"
        result=subprocess.run([sys.executable,str(worker)],input=json.dumps(request),
                              text=True,capture_output=True,timeout=6,check=True)
        output=json.loads(result.stdout)
        self.assertEqual(set(output),{"children"})
        self.assertEqual([x["path"][-1] for x in output["children"]],[[0,1],[1,0]])

    def test_policy_changes_visited_nodes_and_real_attempts(self):
        host=SubprocessSearchHost()
        breadth=host.execute("breadth",TASK, max_attempts=8,seconds=12)
        breadth_trace=list(host.last_trace)
        depth=host.execute("depth",TASK,max_attempts=8,seconds=12)
        depth_trace=list(host.last_trace)
        self.assertEqual(breadth.attempts_used,len(breadth_trace))
        self.assertEqual(depth.attempts_used,len(depth_trace))
        self.assertNotEqual(breadth_trace,depth_trace,
                            "BFS and DFS must actually explore distinct candidate sequences")
        self.assertIsInstance(evaluate_grid(TASK,depth.candidate),EvaluatorResult)
        self.assertLessEqual(breadth.attempts_used,8)
        self.assertLessEqual(depth.attempts_used,8)

    def test_independent_grid_evaluator_catches_forgery(self):
        self.assertEqual(evaluate_grid(TASK,[[0,0],[3,3]]).score,0.0)
        self.assertEqual(evaluate_grid(TASK,[[0,0],[1,0],[1,1],[2,1],[3,3]]).score,0.0)
        solved=[[0,0],[0,1],[0,2],[0,3],[1,3],[2,3],[3,3]]
        self.assertEqual(evaluate_grid(TASK,solved).score,1.0)

    def test_real_reference_agent_used_in_prospective_trial(self):
        host=SubprocessSearchHost()
        with tempfile.TemporaryDirectory() as directory:
            store=HistoryStore(directory)
            trial=ProspectiveExperiment(store)
            created=trial.create(evaluator_id="reference-grid-verifier-v1",
                                 objective="maximize",threshold=1,challenger="depth",
                                 attempt_budget=8,seconds_budget=10,approval=True)
            res=trial.run_task(trial_id=created["id"],task_key="fresh-task-1",
                               task=TASK,execute=host.execute,
                               evaluate=evaluate_grid,approval=True)
            self.assertIn(res["status"],("completed","failed"))
            self.assertEqual(trial.report(created["id"])["assigned_count"],1)
            self.assertGreater(len(host.last_trace),0)
            self.assertEqual(store.stats()["attempt_count"],0)
            self.assertEqual(store.stats()["activity_count"],0)

    def test_invalid_agent_output_or_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            malicious=Path(tmp)/"malicious.py"
            malicious.write_text("import json;print(json.dumps({'children':[{'path':[[0,0],[3,3]],'heuristic':0}]}))")
            host=SubprocessSearchHost([sys.executable,str(malicious)])
            with self.assertRaises(NykraError):
                host.execute("depth",TASK,4,seconds=5)

    def test_failed_external_worker_never_exposes_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            malicious=Path(tmp)/"private_failure.py"
            malicious.write_text("import sys;sys.stderr.write('PRIVATE_CREDENTIAL');sys.exit(9)")
            host=SubprocessSearchHost([sys.executable,str(malicious)])
            with self.assertRaises(NykraError) as context:
                host.execute("breadth",TASK,3,seconds=5)
            self.assertNotIn("PRIVATE",str(context.exception))

    def test_invalid_board_does_not_run_worker(self):
        bad=dict(TASK,walls=[[0,0]])
        with self.assertRaises(NykraError):
            SubprocessSearchHost().execute("breadth",bad,4,seconds=5)

    def test_external_benchmark_requires_approval(self):
        with self.assertRaises(NykraError):
            run_reference_benchmark(count=40,budget=8,approval=False)

    def test_reference_benchmark_is_true_new_search_not_replay(self):
        result=run_reference_benchmark(count=40,budget=10,approval=True)
        self.assertEqual(result["tasks"],40)
        self.assertIn(result["report"]["state_of_evidence"],("advisory_candidate","hold_baseline","not_ready"))
        self.assertFalse(result["report"]["can_auto_apply"])
        self.assertEqual(result["report"]["assigned_count"],40)
        self.assertEqual(result["agent"],"nykra-reference-subprocess-search-agent-no-llm")


if __name__=="__main__":
    unittest.main()
