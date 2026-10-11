"""Synthetic prospective protocol demonstration, completely isolated from live agent data."""
from __future__ import annotations

import json
import tempfile

from .evaluation import EvaluatorResult
from .prospective import ExecutionResult, ProspectiveExperiment
from .store import HistoryStore


def demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="nykra-prospective-") as root:
        experiment = ProspectiveExperiment(HistoryStore(root))
        trial = experiment.create(
            evaluator_id="synthetic-score-v1", objective="maximize",
            threshold=0.5, challenger="depth", approval=True,
            max_tasks=80, min_per_arm=20, attempt_budget=4, seconds_budget=30)
        for i in range(80):
            # Controlled demonstration: the synthetic outcome deliberately
            # depends on assigned policy and is NOT evidence of real benefit.
            experiment.run_task(
                trial_id=trial["id"], task_key=f"synthetic-task-{i:03}",
                task={"fixture": i},
                execute=lambda policy, task, budget, timeout: ExecutionResult(
                    candidate={"synthetic_metric": 0.95 if policy == "depth" else 0.05},
                    attempts_used=budget, cost_units=1),
                evaluate=lambda task, candidate: EvaluatorResult(
                    score=candidate["synthetic_metric"], cost_units=0),
                approval=True)
        experiment.close(trial["id"])
        return {
            "notice": "Synthetic constructed outcomes only. No real agent ran and no policy was deployed.",
            "result": experiment.report(trial["id"]),
        }


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2))
