"""Durable, feedback-driven coding exploration via authorized external model agents.

The host controls branch selection and scoring. A connected agent (such as
ChatGPT using Rel.AI) supplies one candidate only AFTER receiving the previous
evaluation. This module does not itself invoke any model API and does not keep
candidate source files or hidden evaluator cases.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .coding_worker import validate_source
from .exploration_policy import select_next
from .prospective import ProspectiveExperiment
from .relai_coding import EVALUATOR_ID, _TASKS, _cases, _judge
from .store import HistoryStore, NykraError, _identifier

POLICIES = ("breadth", "depth", "adaptive")
MAX_FEEDBACK_EXAMPLES = 3


def _training_feedback(task_id: str, source: str, timeout: float = 3.0) -> dict:
    """Execute candidate in the existing restricted worker, return TRAIN-only feedback."""
    cases = _cases(task_id, heldout=False)
    request = json.dumps({"source": source, "inputs": [arguments for arguments, _ in cases]})
    worker = Path(__file__).with_name("coding_worker.py").resolve()
    env = {k: v for k, v in os.environ.items()
           if k in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix="nykra-iterate-") as directory:
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(worker)], input=request, text=True,
                encoding="utf-8", errors="replace", capture_output=True,
                cwd=directory, env=env, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {"score": 0.0, "passed": 0, "total": len(cases),
                    "failure_examples": [], "worker_status": "unavailable"}
    try:
        if result.returncode != 0 or len(result.stdout) > 30000:
            raise ValueError("worker failed")
        outputs = json.loads(result.stdout)["outputs"]
        if not isinstance(outputs, list) or len(outputs) != len(cases):
            raise ValueError("output count mismatch")
    except (ValueError, TypeError, KeyError):
        return {"score": 0.0, "passed": 0, "total": len(cases),
                "failure_examples": [], "worker_status": "invalid_output"}
    passed = 0
    examples = []
    for (arguments, expected), actual in zip(cases, outputs):
        good = (isinstance(actual, dict) and "value" in actual
                and actual["value"] == expected)
        if good:
            passed += 1
        elif len(examples) < MAX_FEEDBACK_EXAMPLES:
            # Fixtures are synthetic public training inputs, not private files.
            # Never include source code or unbounded interpreter tracebacks.
            examples.append({
                "input": arguments,
                "expected": expected,
                "actual": actual.get("value", "candidate_exception")
                          if isinstance(actual, dict) else "invalid_output",
            })
    return {"score": passed / len(cases), "passed": passed, "total": len(cases),
            "failure_examples": examples, "worker_status": "ok"}


class IterativeCoding:
    """Cooperative model-agent loop. Each step independently validated and persisted."""

    def __init__(self, store: HistoryStore):
        self.store = store
        self.database = store.home / "iterative.sqlite3"
        with self._db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    budget INTEGER NOT NULL,
                    threshold REAL NOT NULL,
                    trial_id TEXT,
                    assignment_id TEXT,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                      ('active','finished','aborted')),
                    started_at REAL NOT NULL,
                    max_seconds REAL NOT NULL,
                    finished_at REAL,
                    final_score REAL,
                    terminal_status TEXT
                );
                CREATE TABLE IF NOT EXISTS steps (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    position INTEGER NOT NULL,
                    parent_id TEXT REFERENCES steps(id),
                    source_digest TEXT NOT NULL,
                    score REAL NOT NULL,
                    feedback_json TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    UNIQUE(session_id,position)
                );
                CREATE INDEX IF NOT EXISTS idx_iterative_steps ON steps(session_id,position);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.store.home.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database, timeout=12)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=12000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def start(self, *, task_id: str, policy: str = "depth", budget: int = 4,
              threshold: float = 1.0, max_seconds: float = 300,
              trial_id: str | None = None, task_key: str | None = None,
              approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required to start a coding-agent session")
        if task_id not in _TASKS or policy not in POLICIES:
            raise NykraError("unsupported coding task or exploration policy")
        if type(budget) is not int or not 1 <= budget <= 16:
            raise NykraError("iterative candidate budget must be 1..16")
        if type(threshold) not in (int, float) or not 0 < threshold <= 1:
            raise NykraError("passing threshold must be in (0,1]")
        if type(max_seconds) not in (int, float) or not 5 <= max_seconds <= 86400:
            raise NykraError("session wall-time limit must be 5..86400 seconds")
        prospective = None
        assignment = None
        if trial_id is not None:
            if task_key is None:
                raise NykraError("prospective session requires unique task key")
            prospective = ProspectiveExperiment(self.store)
            protocol = prospective.get(trial_id)
            if (protocol["evaluator_id"] != EVALUATOR_ID or
                    protocol["objective"] != "maximize" or
                    protocol["threshold"] != threshold):
                raise NykraError("prospective evaluator or objective mismatch")
            if protocol["attempt_budget"] != budget:
                raise NykraError("prospective attempt budget mismatch")
            if protocol["seconds_budget"] != max_seconds:
                raise NykraError("prospective time budget mismatch")
            assignment = prospective.assign(trial_id=trial_id, task_key=task_key)
            if assignment["state"] != "pending":
                raise NykraError("task already assigned/claimed; do not restart")
            policy = assignment["policy"]
            prospective.claim(trial_id=trial_id, assignment_id=assignment["assignment_id"])
        session_id = uuid.uuid4().hex
        run = self.store.create_run(
            task="iterative-coding-" + task_id + "-" + session_id[:12],
            agent="agent-feedback-via-relai", evaluator_id=EVALUATOR_ID)
        try:
            with self._db() as conn:
                conn.execute("""
                    INSERT INTO sessions
                      (id,task_id,policy,budget,threshold,trial_id,assignment_id,
                       run_id,state,started_at,max_seconds)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (session_id, task_id, policy, budget, float(threshold),
                      trial_id, assignment["assignment_id"] if assignment else None,
                      run["id"], "active", time.time(), float(max_seconds)))
        except BaseException:
            if prospective is not None and assignment is not None:
                prospective.finish(
                    trial_id=trial_id, assignment_id=assignment["assignment_id"],
                    status="failed")
            raise
        return self.status(session_id)

    def _load(self, conn: sqlite3.Connection, session_id: str) -> tuple[dict, list[dict]]:
        session_id = _identifier(session_id, "session_id")
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise NykraError("unknown iterative coding session")
        session = dict(row)
        steps = [dict(r) for r in conn.execute(
            "SELECT * FROM steps WHERE session_id=? ORDER BY position", (session_id,))]
        return session, steps

    @staticmethod
    def _select(session: dict, steps: list[dict]) -> dict | None:
        return select_next(
            policy=session["policy"], steps=steps,
            budget=session["budget"], threshold=session["threshold"],
        )

    def status(self, session_id: str) -> dict:
        with self._db() as conn:
            session, steps = self._load(conn, session_id)
        best = max(steps, key=lambda s: (s["score"], -s["position"])) if steps else None
        expired = time.time() >= session["started_at"] + session["max_seconds"]
        next_step = (self._select(session, steps)
                     if session["state"] == "active" and not expired else None)
        # Sanitized training examples are explicit, nonprivate synthetic fixtures.
        previous = steps[-1] if steps else None
        return {
            "session_id": session_id, "task_id": session["task_id"],
            "task_description": _TASKS[session["task_id"]],
            "policy": session["policy"], "state": session["state"],
            "evaluations_used": len(steps), "budget": session["budget"],
            "remaining_seconds": max(0.0, round(
                session["max_seconds"] - (time.time() - session["started_at"]), 1)),
            "best_attempt_id": best["id"] if best else None,
            "best_training_score": best["score"] if best else None,
            "previous_feedback": json.loads(previous["feedback_json"]) if previous else None,
            "request": next_step, "ready_to_finish": bool(steps and
                session["state"] == "active"),
            "trial_id": session["trial_id"], "run_id": session["run_id"],
            "final_score": session["final_score"],
            "terminal_status": session["terminal_status"],
            "source_persisted": False,
        }

    def submit(self, session_id: str, *, source: str, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required before testing candidate code")
        try:
            validate_source(source)
        except (SyntaxError, ValueError):
            raise NykraError("invalid restricted candidate source") from None
        # Claims are serialized using BEGIN IMMEDIATE, guarding concurrent submissions.
        # The session DB is locked during the short worker call; candidate source is
        # never written to either SQLite file.
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session, steps = self._load(conn, session_id)
            if session["state"] != "active":
                raise NykraError("session is not active")
            if time.time() >= session["started_at"] + session["max_seconds"]:
                raise NykraError("session time budget expired")
            request = self._select(session, steps)
            if request is None:
                raise NykraError("session has reached its score or attempt budget")
            started = time.monotonic()
            feedback = _training_feedback(
                session["task_id"], source,
                timeout=min(3.0, max(0.1, session["max_seconds"] -
                                     (time.time() - session["started_at"]))))
            elapsed_ms = (time.monotonic() - started) * 1000
            parent_id = request["parent_attempt_id"]
            attempt = self.store.record_attempt(
                run_id=session["run_id"], parent_id=parent_id, status="ok",
                score=feedback["score"], cost_units=1.0, elapsed_ms=elapsed_ms,
                metadata={"evaluation": "training_only",
                          "candidate_source_persisted": False})
            conn.execute("""
                INSERT INTO steps(id,session_id,position,parent_id,
                                  source_digest,score,feedback_json,duration_ms)
                VALUES (?,?,?,?,?,?,?,?)
            """, (attempt["id"], session_id, len(steps),
                  parent_id, hashlib.sha256(source.encode("utf-8")).hexdigest(),
                  feedback["score"], json.dumps(feedback, separators=(",", ":")),
                  elapsed_ms))
        result = self.status(session_id)
        result["evaluated_attempt_id"] = attempt["id"]
        result["feedback"] = feedback
        return result

    def finish(self, session_id: str, *, best_source: str, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required for held-out evaluation")
        try:
            validate_source(best_source)
        except (ValueError, SyntaxError):
            raise NykraError("invalid final candidate source") from None
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session, steps = self._load(conn, session_id)
            if session["state"] != "active" or not steps:
                raise NykraError("session must be active with evaluated attempts")
            best = max(steps, key=lambda s: (s["score"], -s["position"]))
            if hashlib.sha256(best_source.encode("utf-8")).hexdigest() != best["source_digest"]:
                raise NykraError("final source does not match best evaluated candidate")
            elapsed_ms = (time.time() - session["started_at"]) * 1000
            if session["trial_id"] is not None and elapsed_ms > session["max_seconds"] * 1000:
                status = "timeout_violation"
                score = None
            else:
                score = _judge(session["task_id"], best_source, heldout=True)
                status = "completed"
            if session["trial_id"] is not None:
                ProspectiveExperiment(self.store).finish(
                    trial_id=session["trial_id"], assignment_id=session["assignment_id"],
                    status=status, score=score, attempts_used=len(steps),
                    cost_units=float(len(steps)), elapsed_ms=elapsed_ms)
            conn.execute("""
                UPDATE sessions SET state='finished', finished_at=?,
                    final_score=?, terminal_status=? WHERE id=?
            """, (time.time(), score, status, session_id))
        return self.status(session_id)

    def abort(self, session_id: str, *, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required to abandon active session")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session, steps = self._load(conn, session_id)
            if session["state"] != "active":
                raise NykraError("session already closed")
            if session["trial_id"] is not None:
                ProspectiveExperiment(self.store).finish(
                    trial_id=session["trial_id"], assignment_id=session["assignment_id"],
                    status="failed", attempts_used=len(steps),
                    elapsed_ms=(time.time() - session["started_at"]) * 1000)
            conn.execute(
                "UPDATE sessions SET state='aborted',finished_at=?,terminal_status='failed' WHERE id=?",
                (time.time(), session_id))
        return self.status(session_id)
