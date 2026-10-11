"""Exercise supervised exploration without an LLM, cloud API or shell subprocess."""
from __future__ import annotations

import json
import tempfile

from nykra.controller import Proposal, SupervisedController
from nykra.evaluation import EvaluatorResult
from nykra.intelligence import assess_policies
from nykra.store import HistoryStore


def synthetic_demo() -> dict:
    """Training/held-out *synthetic* traces; never claim real agent gains."""
    with tempfile.TemporaryDirectory(prefix="nykra-intelligence-") as scratch:
        store = HistoryStore(scratch)
        control = SupervisedController(
            store,
            evaluator_id="synthetic-metric-v1",
            approval=True,
            max_attempts=4,
            propose=lambda seen, remaining: (
                Proposal(1) if not seen else
                Proposal(2) if len(seen) == 1 else
                Proposal(10, parent_id=seen[0].attempt_id) if len(seen) == 2 else
                Proposal(3, parent_id=seen[1].attempt_id) if len(seen) == 3 else None
            ),
            evaluate=lambda candidate: EvaluatorResult(float(candidate)),
        )
        # Independently named tasks create a reproducible task-disjoint split.
        for index in range(60):
            control.run(task=f"synthetic-search-{index:03}", agent="synthetic-proposer")
        evaluation = assess_policies(
            store, evaluator_id="synthetic-metric-v1", objective="maximize",
            budget=2, min_train_tasks=8, min_heldout_tasks=8)
        return {
            "notice": "Purely synthetic, constructed candidate tree. Retrospective replay is not an online result.",
            "evaluated_runs": store.stats()["run_count"],
            "evaluated_attempts": store.stats()["attempt_count"],
            "evaluation": evaluation,
        }


if __name__ == "__main__":
    print(json.dumps(synthetic_demo(), indent=2))
