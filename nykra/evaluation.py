"""Explicit, evaluator-backed capture of candidate quality.

Use only from a trusted execution supervisor that can identify the candidate
and the actual evaluator. Generic MCP tool successes are never scored here.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Any

from .store import HistoryStore, NykraError


@dataclass(frozen=True)
class EvaluatorResult:
    """A finite objective metric returned by a supervised evaluator."""

    score: float
    cost_units: float = 1.0
    snapshot_ref: str | None = None


class EvaluatedExploration:
    """Run registered quality evaluations and record measured candidate attempts."""

    def __init__(self, store: HistoryStore, *, evaluator_id: str,
                 evaluate: Callable[[Any], EvaluatorResult]):
        if not isinstance(evaluator_id, str) or not evaluator_id.strip():
            raise NykraError("evaluator_id is required")
        if not callable(evaluate):
            raise NykraError("evaluate must be a callable owned by a trusted supervisor")
        self.store = store
        self.evaluator_id = evaluator_id
        self.evaluate = evaluate

    def begin(self, *, task: str, agent: str, objective: str = "maximize") -> dict:
        return self.store.create_run(task=task, agent=agent, objective=objective,
                                     evaluator_id=self.evaluator_id)

    def attempt(self, *, run_id: str, candidate: Any, attempt_id: str | None = None,
                parent_id: str | None = None) -> dict:
        run = self.store.get_run(run_id)
        if run["evaluator_id"] != self.evaluator_id:
            raise NykraError("evaluator identity differs from recorded run")
        started = time.perf_counter()
        # The candidate is never saved by Nykra; it is handed to the caller's
        # trusted evaluator and only explicit metric/cost/snapshot are recorded.
        try:
            evaluated = self.evaluate(candidate)
        except Exception:
            # Never persist raw exception text, test logs, command lines or paths.
            return self.store.record_attempt(
                run_id=run_id, attempt_id=attempt_id, parent_id=parent_id,
                status="failed", score=None,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                metadata={"evaluation": "trusted_callable", "failure": "evaluator_raised"},
            )
        if not isinstance(evaluated, EvaluatorResult):
            raise NykraError("evaluator must return EvaluatorResult")
        if isinstance(evaluated.score, bool) or not isinstance(evaluated.score, (int, float)) or not math.isfinite(evaluated.score):
            raise NykraError("evaluator returned an invalid objective metric")
        return self.store.record_attempt(
            run_id=run_id, attempt_id=attempt_id, parent_id=parent_id,
            status="ok", score=float(evaluated.score), cost_units=evaluated.cost_units,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            snapshot_ref=evaluated.snapshot_ref,
            metadata={"evaluation": "trusted_callable", "evaluator_id": self.evaluator_id},
        )
