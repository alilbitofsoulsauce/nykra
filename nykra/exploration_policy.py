"""Agent-independent, deterministic exploration decisions.

This module never imports Rel.AI, Codex, any model SDK or a code evaluator.
Hosts use the same scored-attempt ancestry to choose the next branch.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

POLICIES = ("breadth", "depth", "adaptive")


def select_next(
    *, policy: str, steps: Sequence[Mapping[str, Any]],
    budget: int, threshold: float = 1.0,
) -> dict[str, str | None] | None:
    """Select a new independent root or an existing evaluated parent.

    Entries contain id, parent_id, score and position fields.
    The ordered attempt history is validated before any decision.
    """
    if policy not in POLICIES:
        raise ValueError("unsupported exploration policy")
    if type(budget) is not int or budget < 1:
        raise ValueError("attempt budget must be a positive integer")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("threshold must be a finite proportion within (0, 1]")
    if len(steps) > budget:
        raise ValueError("attempt history exceeds the prespecified budget")

    indexed: dict[str, Mapping[str, Any]] = {}
    depths: dict[str, int] = {}
    children: dict[str, int] = {}
    roots = []
    for position, attempt in enumerate(steps):
        id_ = attempt["id"]
        parent = attempt["parent_id"]
        score = attempt["score"]
        if not isinstance(id_, str) or not id_ or id_ in indexed:
            raise ValueError("attempt IDs must be distinct nonempty strings")
        if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("attempt scores must be finite proportions")
        if type(attempt["position"]) is not int or attempt["position"] != position:
            raise ValueError("attempts must be in contiguous chronological order")
        if parent is not None and (not isinstance(parent, str) or parent not in indexed):
            raise ValueError("parent must precede its child in the attempt history")
        indexed[id_] = attempt
        depths[id_] = depths[parent] + 1 if parent is not None else 0
        children[id_] = 0
        if parent is None:
            roots.append(attempt)
        else:
            children[parent] += 1

    if len(steps) >= budget or any(attempt["score"] >= threshold for attempt in steps):
        return None
    if not steps or (policy == "breadth" and len(roots) < 2):
        return {"kind": "new_root", "parent_attempt_id": None}
    if policy == "breadth":
        chosen = min(steps, key=lambda s: (
            depths[s["id"]], children[s["id"]], s["position"],
        ))
    elif policy == "depth":
        chosen = steps[-1]
    else:
        if (len(roots) < 2 and len(steps) >= 3 and
            all(steps[-i]["score"] <= steps[-i-1]["score"] for i in (1, 2))):
            return {"kind": "new_root", "parent_attempt_id": None}
        chosen = max(steps, key=lambda s: (s["score"], s["position"]))
    return {"kind": "revise", "parent_attempt_id": chosen["id"]}
