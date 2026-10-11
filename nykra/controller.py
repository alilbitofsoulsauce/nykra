"""Opt-in, supervisor-owned candidate exploration.

Nykra does not spawn commands, execute models, edit files, or supply remote
agent prompts. The host owns the callbacks, side effects, approval and sandbox.
Candidates remain in memory and are never stored in the history database.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from .evaluation import EvaluatedExploration, EvaluatorResult
from .store import HistoryStore, NykraError


@dataclass(frozen=True)
class Proposal:
    """One candidate, optionally branching from an already evaluated attempt."""
    candidate: Any
    parent_id: str | None = None


@dataclass(frozen=True)
class Observation:
    attempt_id: str
    parent_id: str | None
    status: str
    score: float | None
    elapsed_ms: float
    cost_units: float


class SupervisedController:
    """Bounded exploration delegated to two trusted, caller-controlled callbacks.

    propose(immutable_observations, remaining_attempts) -> Proposal | None
    evaluate(candidate) -> EvaluatorResult

    An explicit approval is required before the callbacks are invoked. Candidate
    values never enter stored metadata; callbacks execute in the caller process.
    """

    def __init__(self, store: HistoryStore, *, evaluator_id: str,
                 propose: Callable[[tuple[Observation, ...], int], Proposal | None],
                 evaluate: Callable[[Any], EvaluatorResult],
                 max_attempts: int = 8, max_seconds: float = 120,
                 approval: bool = False):
        if not callable(propose) or not callable(evaluate):
            raise NykraError("propose and evaluate must be trusted callables")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 1000:
            raise NykraError("max_attempts must be in 1..1000")
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (float, int)) or not math.isfinite(max_seconds) or not (0 < max_seconds <= 86400):
            raise NykraError("max_seconds must be a finite duration in (0, 86400]")
        self.store = store
        self.evaluator = EvaluatedExploration(store, evaluator_id=evaluator_id, evaluate=evaluate)
        self.propose = propose
        self.max_attempts = max_attempts
        self.max_seconds = float(max_seconds)
        self.approval = approval is True

    def run(self, *, task: str, agent: str, objective: str = "maximize") -> dict:
        if not self.approval:
            raise NykraError("explicit approval is required to invoke supervised callbacks")
        # No events or runs are recorded when approval is absent.
        run = self.evaluator.begin(task=task, agent=agent, objective=objective)
        history: list[Observation] = []
        seen: set[str] = set()
        begun = time.monotonic()
        reason = "budget_exhausted"
        for index in range(self.max_attempts):
            if time.monotonic() - begun >= self.max_seconds:
                reason = "time_limit"
                break
            try:
                proposal = self.propose(tuple(history), self.max_attempts - index)
            except Exception as exc:
                # Host callbacks may contain confidential state. Do not echo it.
                raise NykraError("trusted proposer raised an exception; run may be incomplete") from None
            if proposal is None:
                reason = "proposer_finished"
                break
            if not isinstance(proposal, Proposal):
                raise NykraError("proposer must return Proposal or None")
            if proposal.parent_id is not None and proposal.parent_id not in seen:
                raise NykraError("proposed parent must be an already evaluated attempt in this run")
            # Run-time and max-count checks are cooperative. A blocking or malicious
            # host callback needs host-level process isolation and termination.
            attempt = self.evaluator.attempt(
                run_id=run["id"], candidate=proposal.candidate, parent_id=proposal.parent_id)
            seen.add(attempt["id"])
            history.append(Observation(
                attempt_id=attempt["id"], parent_id=attempt["parent_id"],
                status=attempt["status"], score=attempt["score"],
                elapsed_ms=attempt["elapsed_ms"], cost_units=attempt["cost_units"]))
        return {
            "run_id": run["id"],
            "evaluator_id": run["evaluator_id"],
            "objective": objective,
            "attempt_count": len(history),
            "completed": reason in ("proposer_finished", "budget_exhausted"),
            "stop_reason": reason,
            "observations": [
                {"attempt_id": item.attempt_id, "parent_id": item.parent_id,
                 "status": item.status, "score": item.score,
                 "elapsed_ms": item.elapsed_ms, "cost_units": item.cost_units}
                for item in history
            ],
            "activation": "explicitly_approved_host_callbacks",
            "external_side_effects": "owned_by_host",
        }
