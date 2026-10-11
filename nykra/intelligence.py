"""Retrospective policy assessment, with task-disjoint held-out recommendations.

No replay can infer the results of actions absent from a recorded exploration
tree. This module NEVER changes a live agent policy or advertises a causal gain.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Any

from .replay import POLICIES, replay
from .store import HistoryStore, NykraError

BASELINE = "breadth"
CANDIDATES = tuple(p for p in POLICIES if p != BASELINE)


def _partition(evaluator_id: str, task: str, fraction: float) -> str:
    # Stable, task-disjoint groups. Task text never appears in the output.
    digest = hashlib.sha256((evaluator_id + "\0" + task.strip()).encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return "heldout" if value < fraction else "training"


def _success_utility(best: float | None, objective: str, low: float, high: float) -> float:
    if best is None:
        return 0.0
    if high <= low:
        return 1.0
    return min(1.0, max(0.0, (best - low if objective == "maximize" else high - best) / (high - low)))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _paired_one_sided_sign_p(deltas: list[float]) -> dict[str, Any]:
    """Exact sign-test p-value for a positive paired median, ignoring exact ties."""
    usable = [x for x in deltas if not math.isclose(x, 0.0, rel_tol=0, abs_tol=1e-12)]
    wins = sum(x > 0 for x in usable)
    losses = len(usable) - wins
    n = len(usable)
    p = min(1.0, math.fsum(math.comb(n, k) / 2**n for k in range(wins, n + 1))) if n else 1.0
    return {"wins": wins, "losses": losses, "ties": len(deltas) - n,
            "p_value": round(p, 8), "independent_non_ties": n}


def assess_policies(store: HistoryStore, *, evaluator_id: str, objective: str = "maximize",
                    budget: int = 2, holdout_fraction: float = 0.33,
                    min_train_tasks: int = 8, min_heldout_tasks: int = 8) -> dict[str, Any]:
    if not isinstance(evaluator_id, str) or not evaluator_id.strip() or len(evaluator_id) > 256:
        raise NykraError("evaluator_id is required")
    if objective not in ("maximize", "minimize"):
        raise NykraError("objective must be maximize or minimize")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 1000:
        raise NykraError("budget must be between 1 and 1000")
    if not isinstance(holdout_fraction, (int, float)) or isinstance(holdout_fraction, bool) or not 0.1 <= holdout_fraction <= 0.5:
        raise NykraError("holdout_fraction must be in [0.1, 0.5]")
    for name, count in [("min_train_tasks", min_train_tasks), ("min_heldout_tasks", min_heldout_tasks)]:
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 1000:
            raise NykraError(f"{name} must be an integer in 2..1000")

    base = {
        "mode": "retrospective_task_disjoint_holdout",
        "scope": "recorded_outcomes_only",
        "evaluator_id": evaluator_id,
        "objective": objective,
        "budget": budget,
        "baseline_policy": BASELINE,
        "holdout_fraction": holdout_fraction,
        "agent_policy_modified": False,
        "can_auto_apply": False,
        "recommendation": None,
        "status": "insufficient_evidence",
        "qualification": (
            "Task-disjoint evaluation on recorded candidate trees. Outcomes for "
            "untried branches cannot be estimated; selection effects and replay "
            "bias remain. No causal improvement or live-agent generalization is claimed."
        ),
    }
    all_runs = store.list_runs(limit=1000)
    if len(all_runs) >= 1000:
        return {**base, "reason": "run_inventory_truncated_at_1000"}
    relevant = [r for r in all_runs if r["evaluator_id"] == evaluator_id and r["objective"] == objective]
    task_counts = Counter(r["task"].strip() for r in relevant)
    duplicate_tasks = {task for task, count in task_counts.items() if count != 1}
    excluded = {"duplicate_task_runs": 0, "insufficient_attempts": 0,
                "insufficient_scores": 0}

    data: dict[str, list[dict]] = {"training": [], "heldout": []}
    for run in relevant:
        if run["task"].strip() in duplicate_tasks:
            excluded["duplicate_task_runs"] += 1
            continue
        attempts = store.list_attempts(run["id"])
        if len(attempts) < budget:
            excluded["insufficient_attempts"] += 1
            continue
        values = [a["score"] for a in attempts if a["status"] == "ok"]
        if len(values) < 2:
            excluded["insufficient_scores"] += 1
            continue
        low, high = min(values), max(values)
        normalized = {}
        for policy in POLICIES:
            result = replay(store, run_id=run["id"], policy=policy, budget=budget, workers=1)
            normalized[policy] = _success_utility(result["best_score"], objective, low, high)
        bucket = _partition(evaluator_id, run["task"], holdout_fraction)
        data[bucket].append({"run_id": run["id"], "utility": normalized})

    train, heldout = data["training"], data["heldout"]
    sizes = {"training_tasks": len(train), "heldout_tasks": len(heldout),
             "eligible_tasks": len(train) + len(heldout), "excluded": excluded,
             "original_runs": len(relevant)}
    if len(train) < min_train_tasks or len(heldout) < min_heldout_tasks:
        return {**base, **sizes, "reason": "insufficient_task_disjoint_samples"}

    train_delta = {
        policy: _mean([row["utility"][policy] - row["utility"][BASELINE] for row in train])
        for policy in CANDIDATES
    }
    # Only training data can choose the candidate, never held-out outcomes.
    winner = max(CANDIDATES, key=lambda policy: train_delta[policy])
    if train_delta[winner] <= 0:
        return {**base, **sizes, "status": "hold_baseline", "reason": "no_training_lift",
                "training_deltas": {k: round(v, 6) for k, v in train_delta.items()}}
    differences = [
        row["utility"][winner] - row["utility"][BASELINE] for row in heldout
    ]
    sign = _paired_one_sided_sign_p(differences)
    mean_heldout = _mean(differences)
    gate = sign["p_value"] <= 0.05 and mean_heldout > 0 and sign["independent_non_ties"] >= min_heldout_tasks
    return {
        **base, **sizes,
        "status": "advisory_candidate" if gate else "hold_baseline",
        "reason": "retrospective_gate_passed" if gate else "heldout_evidence_not_convincing",
        "selected_using_training_only": winner,
        "training_deltas": {k: round(v, 6) for k, v in train_delta.items()},
        "heldout_mean_normalized_delta": round(mean_heldout, 6),
        "heldout_sign_test": sign,
        "recommendation": (
            {"policy": winner, "mode": "advisory_only",
             "requires_explicit_host_approval": True,
             "next_step": "Prospective, controlled online evaluation before policy deployment"}
            if gate else None
        ),
        "heldout_run_ids": [row["run_id"] for row in heldout],
        "training_run_ids": [row["run_id"] for row in train],
    }
