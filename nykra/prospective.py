"""Opt-in prospective policy experiments with durable, randomized task allocation.

This is a protocol for a trusted execution host, NOT an agent runtime hook.
No arbitrary commands, prompts, candidate payloads or model APIs are stored.
A separate SQLite file avoids changing the live background-observer schema.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .evaluation import EvaluatorResult
from .replay import POLICIES
from .store import HistoryStore, NykraError, _identifier, _nonnegative, _score


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ExecutionResult:
    """Trusted host's output after a policy-controlled execution.

    attempts_used and cost_units are attestations by the authorized host.
    An agent's self-reported metric must not be treated as evaluator truth.
    """
    candidate: Any
    attempts_used: int
    cost_units: float = 0.0


def _wilson(success: int, total: int) -> list[float] | None:
    if not total:
        return None
    p = success / total
    z = 1.959963984540054
    den = 1 + z*z/total
    middle = (p + z*z/(2*total)) / den
    margin = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / den
    return [round(max(0.0, middle-margin), 6), round(min(1.0, middle+margin), 6)]


def _fisher_one_sided(csuccess: int, ctotal: int, bsuccess: int, btotal: int) -> float:
    """Exact conditional one-sided p-value for challenger success rate > baseline."""
    total = ctotal + btotal
    successes = csuccess + bsuccess
    denominator = math.comb(total, ctotal)
    upper = min(ctotal, successes)
    p = math.fsum(
        math.comb(successes, k) * math.comb(total-successes, ctotal-k) / denominator
        for k in range(csuccess, upper+1)
        if 0 <= ctotal-k <= total-successes
    )
    return min(1.0, p)


class ProspectiveExperiment:
    """Persist task assignment BEFORE host execution, with intent-to-treat records."""

    def __init__(self, store: HistoryStore):
        self.home = store.home
        self.database = self.home / "prospective.sqlite3"
        with self._db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trials(
                    id TEXT PRIMARY KEY, evaluator_id TEXT NOT NULL,
                    objective TEXT NOT NULL CHECK(objective IN ('maximize','minimize')),
                    threshold REAL NOT NULL, challenger TEXT NOT NULL,
                    attempt_budget INTEGER NOT NULL,
                    seconds_budget REAL NOT NULL,
                    max_tasks INTEGER NOT NULL,
                    min_per_arm INTEGER NOT NULL,
                    min_effect REAL NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('open','closed')),
                    secret TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS assignments(
                    id TEXT PRIMARY KEY,
                    trial_id TEXT NOT NULL REFERENCES trials(id),
                    task_digest TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('pending','running','completed','failed','budget_violation','timeout_violation')),
                    score REAL, success INTEGER,
                    attempts_used INTEGER, cost_units REAL, elapsed_ms REAL,
                    assigned_at TEXT NOT NULL, finished_at TEXT,
                    UNIQUE(trial_id, task_digest)
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_arm ON assignments(trial_id, policy, state);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.home.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.database), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create(self, *, evaluator_id: str, objective: str, threshold: float,
               challenger: str, approval: bool = False, attempt_budget: int = 6,
               seconds_budget: float = 180, max_tasks: int = 200,
               min_per_arm: int = 20, min_effect: float = 0.05) -> dict:
        if approval is not True:
            raise NykraError("explicit host approval is required to create a prospective experiment")
        evaluator_id = _identifier(evaluator_id, "evaluator_id")
        if objective not in ("maximize", "minimize"):
            raise NykraError("objective must be maximize or minimize")
        threshold = _score(threshold)
        if challenger not in POLICIES or challenger == "breadth":
            raise NykraError("challenger must be a supported non-baseline policy")
        if isinstance(attempt_budget, bool) or not isinstance(attempt_budget, int) or not 1 <= attempt_budget <= 1000:
            raise NykraError("attempt_budget must be in 1..1000")
        seconds_budget = _nonnegative(seconds_budget, "seconds_budget")
        if not 0 < seconds_budget <= 86400:
            raise NykraError("seconds_budget must be in (0,86400]")
        if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or not 40 <= max_tasks <= 500:
            raise NykraError("max_tasks must be 40..500")
        if isinstance(min_per_arm, bool) or not isinstance(min_per_arm, int) or not 10 <= min_per_arm <= max_tasks // 2:
            raise NykraError("min_per_arm must be 10..max_tasks/2")
        if isinstance(min_effect, bool) or not isinstance(min_effect, (float, int)) or not math.isfinite(min_effect) or not 0 <= min_effect <= 1:
            raise NykraError("min_effect must be a finite proportion in [0,1]")
        row = dict(id=uuid.uuid4().hex, evaluator_id=evaluator_id, objective=objective,
                   threshold=threshold, challenger=challenger, attempt_budget=attempt_budget,
                   seconds_budget=seconds_budget, max_tasks=max_tasks, min_per_arm=min_per_arm,
                   min_effect=float(min_effect), state="open",
                   secret=secrets.token_hex(32), created_at=_now(), closed_at=None)
        with self._db() as conn:
            conn.execute("""
                INSERT INTO trials(id,evaluator_id,objective,threshold,challenger,
                                   attempt_budget,seconds_budget,max_tasks,min_per_arm,min_effect,
                                   state,secret,created_at,closed_at)
                VALUES (:id,:evaluator_id,:objective,:threshold,:challenger,
                        :attempt_budget,:seconds_budget,:max_tasks,:min_per_arm,:min_effect,
                        :state,:secret,:created_at,:closed_at)
            """, row)
        return self.get(row["id"])

    def get(self, trial_id: str) -> dict:
        trial_id = _identifier(trial_id, "trial_id")
        with self._db() as conn:
            row = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
        if row is None:
            raise NykraError("unknown prospective trial")
        result = dict(row)
        result.pop("secret")
        return result

    def _digest(self, conn: sqlite3.Connection, trial_id: str, task_key: str) -> str:
        row = conn.execute("SELECT secret FROM trials WHERE id=?", (trial_id,)).fetchone()
        if row is None:
            raise NykraError("unknown prospective trial")
        return hmac.new(bytes.fromhex(row["secret"]), task_key.encode("utf-8"), hashlib.sha256).hexdigest()

    def assign(self, *, trial_id: str, task_key: str) -> dict:
        """Idempotent assignment, committed before host receives a policy."""
        trial_id = _identifier(trial_id, "trial_id")
        task_key = _identifier(task_key, "task_key")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            trial = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
            if trial is None:
                raise NykraError("unknown prospective trial")
            digest = self._digest(conn, trial_id, task_key)
            old = conn.execute("SELECT * FROM assignments WHERE trial_id=? AND task_digest=?",
                               (trial_id, digest)).fetchone()
            if old is not None:
                return self._public_assignment(old, trial)
            if trial["state"] != "open":
                raise NykraError("trial is closed; no new assignments allowed")
            count = conn.execute("SELECT COUNT(*) FROM assignments WHERE trial_id=?", (trial_id,)).fetchone()[0]
            if count >= trial["max_tasks"]:
                raise NykraError("prespecified task allocation limit reached")
            policy = ("breadth", trial["challenger"])[secrets.randbelow(2)]
            values = dict(id=uuid.uuid4().hex, trial_id=trial_id, task_digest=digest,
                          policy=policy, state="pending", assigned_at=_now())
            conn.execute("""
                INSERT INTO assignments(id,trial_id,task_digest,policy,state,assigned_at)
                VALUES (:id,:trial_id,:task_digest,:policy,:state,:assigned_at)
            """, values)
            return self._public_assignment(values, trial)

    @staticmethod
    def _public_assignment(row: Any, trial: Any) -> dict:
        return {
            "assignment_id": row["id"], "trial_id": row["trial_id"],
            "policy": row["policy"], "state": row["state"],
            "attempt_budget": trial["attempt_budget"],
            "seconds_budget": trial["seconds_budget"],
            "evaluator_id": trial["evaluator_id"],
            "objective": trial["objective"],
            "threshold": trial["threshold"],
        }

    def claim(self, *, trial_id: str, assignment_id: str) -> dict:
        trial_id = _identifier(trial_id, "trial_id")
        assignment_id = _identifier(assignment_id, "assignment_id")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            trial = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
            if trial is None or trial["state"] != "open":
                raise NykraError("trial not open")
            changed = conn.execute(
                "UPDATE assignments SET state='running' WHERE id=? AND trial_id=? AND state='pending'",
                (assignment_id, trial_id))
            if changed.rowcount != 1:
                raise NykraError("assignment missing or already claimed; no duplicate execution")
            row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
            return self._public_assignment(row, trial)

    def finish(self, *, trial_id: str, assignment_id: str, status: str,
               score: float | None = None, attempts_used: int | None = None,
               cost_units: float | None = None, elapsed_ms: float | None = None) -> dict:
        if status not in ("completed", "failed", "budget_violation", "timeout_violation"):
            raise NykraError("invalid terminal assignment state")
        if status == "completed":
            score = _score(score)
        elif score is not None:
            score = _score(score)
        if attempts_used is not None and (isinstance(attempts_used, bool) or not isinstance(attempts_used, int) or attempts_used < 0):
            raise NykraError("attempts_used must be a non-negative integer")
        if cost_units is not None:
            cost_units = _nonnegative(cost_units, "cost_units")
        if elapsed_ms is not None:
            elapsed_ms = _nonnegative(elapsed_ms, "elapsed_ms")
        trial_id = _identifier(trial_id, "trial_id")
        assignment_id = _identifier(assignment_id, "assignment_id")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            trial = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
            if trial is None or trial["state"] != "open":
                raise NykraError("trial not open")
            row = conn.execute(
                "SELECT * FROM assignments WHERE id=? AND trial_id=?", (assignment_id, trial_id)
            ).fetchone()
            if row is None or row["state"] not in ("pending", "running"):
                raise NykraError("assignment already finalized or unknown")
            if status == "completed" and (row["state"] != "running" or attempts_used is None or elapsed_ms is None):
                raise NykraError("completed outcome requires claimed assignment and measured effort")
            if status == "completed" and attempts_used > trial["attempt_budget"]:
                raise NykraError("attempt budget exceeded; record budget_violation instead")
            if status == "completed" and elapsed_ms > trial["seconds_budget"] * 1000:
                raise NykraError("time budget exceeded; record timeout_violation instead")
            passed = (score >= trial["threshold"] if trial["objective"] == "maximize"
                      else score <= trial["threshold"]) if status == "completed" else False
            conn.execute("""
                UPDATE assignments SET state=?, score=?, success=?, attempts_used=?,
                        cost_units=?, elapsed_ms=?, finished_at=?
                WHERE id=? AND trial_id=?
            """, (status, score, int(passed), attempts_used, cost_units,
                  elapsed_ms, _now(), assignment_id, trial_id))
        return {"assignment_id": assignment_id, "trial_id": trial_id, "status": status,
                "passed": bool(passed), "score": score}

    def close(self, trial_id: str) -> dict:
        trial_id = _identifier(trial_id, "trial_id")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
            if row is None:
                raise NykraError("unknown trial")
            pending = conn.execute(
                "SELECT COUNT(*) FROM assignments WHERE trial_id=? AND state IN ('pending','running')",
                (trial_id,)).fetchone()[0]
            if pending:
                raise NykraError("cannot close: explicitly finalize missing/abandoned assignments as failed")
            if row["state"] == "open":
                conn.execute("UPDATE trials SET state='closed', closed_at=? WHERE id=?",
                             (_now(), trial_id))
        return self.get(trial_id)

    def report(self, trial_id: str) -> dict:
        trial = self.get(trial_id)
        with self._db() as conn:
            rows = conn.execute(
                "SELECT policy,state,success,score,attempts_used,cost_units,elapsed_ms "
                "FROM assignments WHERE trial_id=?", (trial_id,)).fetchall()
        arms = {}
        for policy in ("breadth", trial["challenger"]):
            subset = [r for r in rows if r["policy"] == policy]
            successes = sum(r["success"] == 1 for r in subset)
            completed = sum(r["state"] not in ("pending", "running") for r in subset)
            measured = [r for r in subset if r["score"] is not None]
            arms[policy] = {
                "assigned": len(subset), "finalized": completed,
                "pending_or_running": len(subset)-completed,
                "passes": successes,
                "failures_or_violations": sum(r["state"] in ("failed","budget_violation","timeout_violation") for r in subset),
                "success_rate_intent_to_treat": round(successes/len(subset), 6) if subset else None,
                "wilson_95_interval": _wilson(successes, len(subset)),
                "mean_evaluator_score_observed_only": (
                    round(sum(r["score"] for r in measured)/len(measured), 6)
                    if measured else None
                ),
            }
        b, c = arms["breadth"], arms[trial["challenger"]]
        safe = (trial["state"] == "closed" and
                b["assigned"] >= trial["min_per_arm"] and c["assigned"] >= trial["min_per_arm"] and
                b["pending_or_running"] == 0 and c["pending_or_running"] == 0)
        gate = None
        p = None
        difference = None
        if safe:
            difference = c["passes"]/c["assigned"] - b["passes"]/b["assigned"]
            p = _fisher_one_sided(c["passes"], c["assigned"], b["passes"], b["assigned"])
            gate = p <= 0.05 and difference >= trial["min_effect"]
        return {
            "trial_id": trial_id,
            "state": trial["state"],
            "protocol": {
                "baseline": "breadth", "challenger": trial["challenger"],
                "evaluator_id": trial["evaluator_id"], "objective": trial["objective"],
                "threshold": trial["threshold"], "attempt_budget": trial["attempt_budget"],
                "seconds_budget": trial["seconds_budget"], "min_per_arm": trial["min_per_arm"],
                "min_effect": trial["min_effect"], "alpha": 0.05,
            },
            "assigned_count": len(rows), "max_tasks": trial["max_tasks"], "arms": arms,
            "state_of_evidence": (
                "advisory_candidate" if gate is True else
                "hold_baseline" if safe else "not_ready"
            ),
            "reason": (
                "prospective_signal_meets_prespecified_gate" if gate is True else
                "prospective_gate_not_met" if safe else
                "trial_must_be_closed_with_minimum_complete_arms"
            ),
            "challenger_minus_baseline_success_rate": round(difference, 6) if difference is not None else None,
            "fisher_one_sided_p": p,  # preserve tiny nonzero p-values in scientific notation
            "candidate_policy": trial["challenger"] if gate else None,
            "can_auto_apply": False, "agent_policies_modified": False,
            "qualification": (
                "Randomized per-task prospective protocol with trusted host-supplied outcomes. "
                "The host must actually execute assigned policies, enforce resource limits, "
                "and evaluate independently. This code does not prove host compliance, "
                "causality, model improvement or suitability for unattended deployment."
            ),
        }

    def run_task(self, *, trial_id: str, task_key: str, task: Any,
                 execute: Callable[[str, Any, int, float], ExecutionResult],
                 evaluate: Callable[[Any, Any], EvaluatorResult],
                 approval: bool = False) -> dict:
        """Host-owned execution; records assignment before invoking either callback."""
        if approval is not True:
            raise NykraError("explicit approval required before host code execution")
        if not callable(execute) or not callable(evaluate):
            raise NykraError("trusted execute and evaluate callbacks required")
        allocated = self.assign(trial_id=trial_id, task_key=task_key)
        claimed = self.claim(trial_id=trial_id, assignment_id=allocated["assignment_id"])
        start = time.monotonic()
        result: ExecutionResult | None = None
        measured: EvaluatorResult | None = None
        try:
            result = execute(claimed["policy"], task, claimed["attempt_budget"], claimed["seconds_budget"])
            if not isinstance(result, ExecutionResult):
                raise ValueError("untrusted execution result")
            if isinstance(result.attempts_used, bool) or not isinstance(result.attempts_used, int) or result.attempts_used < 0:
                raise ValueError("invalid attempt count")
            _nonnegative(result.cost_units, "cost_units")
            if result.attempts_used <= claimed["attempt_budget"]:
                measured = evaluate(task, result.candidate)
                if not isinstance(measured, EvaluatorResult):
                    raise ValueError("invalid evaluator result")
                _score(measured.score)
                _nonnegative(measured.cost_units, "cost_units")
        except Exception:
            # Do not expose prompts, file paths, command text or exception messages.
            return self.finish(trial_id=trial_id, assignment_id=claimed["assignment_id"],
                               status="failed",
                               attempts_used=result.attempts_used if isinstance(result, ExecutionResult) and
                               isinstance(result.attempts_used, int) and not isinstance(result.attempts_used, bool) and result.attempts_used >= 0 else None,
                               elapsed_ms=(time.monotonic()-start)*1000)
        elapsed_ms = (time.monotonic()-start)*1000
        status = ("budget_violation" if result.attempts_used > claimed["attempt_budget"] else
                  "timeout_violation" if elapsed_ms > claimed["seconds_budget"]*1000 else
                  "completed")
        return self.finish(trial_id=trial_id, assignment_id=claimed["assignment_id"],
                           status=status, score=measured.score if measured else None,
                           attempts_used=result.attempts_used,
                           cost_units=result.cost_units+(measured.cost_units if measured else 0),
                           elapsed_ms=elapsed_ms)
