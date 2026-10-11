"""Prefix-observable, deterministic replay of recorded exploration trees.

Offline replay reveals only existing outcomes. It does not simulate the result
of a previously unexecuted action or establish a causal performance improvement.
"""

from __future__ import annotations

import math
from typing import Any

from .store import HistoryStore, NykraError

POLICIES = ("breadth", "depth", "adaptive")


def _depths(records: list[dict[str, Any]]) -> dict[str, int]:
    """Parents must have been inserted before children by HistoryStore."""
    depths: dict[str, int] = {}
    for node in records:
        parent = node["parent_id"]
        if parent is not None and parent not in depths:
            raise NykraError("invalid discovery tree: missing or out-of-order parent")
        depths[node["id"]] = 0 if parent is None else depths[parent] + 1
    return depths


def _rank(legal: list[dict[str, Any]], visible: dict[str, dict[str, Any]],
          policy: str, objective: str, selected_count: int) -> list[dict[str, Any]]:
    """No unrevealed attempt scores, status, or metadata enter policy decisions."""
    if policy == "breadth":
        return sorted(legal, key=lambda n: (n["depth"], n["order"]))
    if policy == "depth":
        return sorted(legal, key=lambda n: (-n["depth"], n["order"]))

    good_scores = [(n["score"] if objective == "maximize" else -n["score"])
                   for n in visible.values() if n["status"] == "ok"]
    best = max(good_scores) if good_scores else None

    def priority(node: dict[str, Any]) -> tuple[float, int]:
        parent = visible.get(node["parent_id"])
        # Regularly reserve an opening for an unseen root when available.
        if parent is None:
            return (1.0 if selected_count % 3 == 0 else -0.25, -node["order"])
        if parent["status"] != "ok":
            # Repairable failures remain candidates, but are deprioritized.
            return (-0.50, -node["order"])
        value = parent["score"] if objective == "maximize" else -parent["score"]
        relative = 0.0 if best is None else value - best
        return (0.75 + max(-1.0, relative) + min(0.2, node["depth"] * 0.025),
                -node["order"])

    return sorted(legal, key=priority, reverse=True)


def replay(store: HistoryStore, *, run_id: str, policy: str = "adaptive",
           budget: int | None = None, workers: int = 1,
           cost_weight: float = 0.0, parallelism_weight: float = 0.0) -> dict[str, Any]:
    if policy not in POLICIES:
        raise NykraError(f"unknown replay policy: {policy}")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 128:
        raise NykraError("workers must be between 1 and 128")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or budget < 0):
        raise NykraError("budget must be a non-negative integer")
    if not isinstance(cost_weight, (int, float)) or not math.isfinite(cost_weight) or cost_weight < 0:
        raise NykraError("cost_weight must be finite and non-negative")
    if not isinstance(parallelism_weight, (int, float)) or not math.isfinite(parallelism_weight) or parallelism_weight < 0:
        raise NykraError("parallelism_weight must be finite and non-negative")

    run = store.get_run(run_id)
    records = store.list_attempts(run_id)
    depths = _depths(records)
    allowed = len(records) if budget is None else min(budget, len(records))
    # This private map is read only when a historical outcome is explicitly revealed.
    hidden = {n["id"]: n for n in records}
    visible: dict[str, dict[str, Any]] = {}
    revealed: list[str] = []
    attainment: list[float | None] = []
    round_count = 0
    total_cost = 0.0
    total_elapsed = 0.0
    best: float | None = None

    while len(revealed) < allowed:
        # The policy gets structural frontiers, not their unobserved outcomes.
        legal = [
            {"id": n["id"], "parent_id": n["parent_id"],
             "depth": depths[n["id"]], "order": index}
            for index, n in enumerate(records)
            if n["id"] not in visible
            and (n["parent_id"] is None or n["parent_id"] in visible)
        ]
        if not legal:
            break
        candidates = _rank(legal, visible, policy, run["objective"], len(revealed))
        # Select an independent batch from the same revealed prefix.
        batch = candidates[:min(workers, allowed - len(revealed))]
        round_count += 1
        for chosen in batch:
            observed = hidden[chosen["id"]]
            visible[chosen["id"]] = observed
            revealed.append(observed["id"])
            total_cost += observed["cost_units"]
            total_elapsed += observed["elapsed_ms"]
            if observed["status"] == "ok":
                score = observed["score"]
                if best is None or (score > best if run["objective"] == "maximize" else score < best):
                    best = score
            attainment.append(best)

    oriented = (best if run["objective"] == "maximize" else -best) if best is not None else None
    reward = (oriented - cost_weight * total_cost +
              parallelism_weight * len(revealed) / max(1, round_count)) if oriented is not None else None
    return {
        "run_id": run_id,
        "policy": policy,
        "objective": run["objective"],
        "budget": allowed,
        "workers": workers,
        "revealed_attempt_ids": revealed,
        "replayed_attempts": len(revealed),
        "recorded_attempts": len(records),
        "decision_rounds": round_count,
        "total_cost_units": round(total_cost, 8),
        "total_elapsed_ms": round(total_elapsed, 8),
        "best_score": best,
        "reward": reward,
        "attainment_curve": attainment,
        "replay_scope": "recorded_outcomes_only",
        "qualification": (
            "Historical replay, not a counterfactual oracle. Unknown actions and "
            "unobserved outcomes cannot be inferred from this trace."
        ),
    }
