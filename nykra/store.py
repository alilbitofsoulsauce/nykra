"""Versioned SQLite history store. No agent-specific dependency or network service."""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import SCHEMA_VERSION


class NykraError(ValueError):
    """An invalid user request or incompatible local store."""


def default_home() -> Path:
    override = os.environ.get("NYKRA_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "Nykra"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "nykra"


def _required_text(value: Any, field: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise NykraError(f"{field} must be non-empty text of at most {maximum} characters")
    return value.strip()


def _identifier(value: Any, field: str, maximum: int = 256) -> str:
    value = _required_text(value, field, maximum)
    if not re.fullmatch(r"[a-zA-Z0-9_./:@-]+", value):
        raise NykraError(f"{field} must be a simple identifier")
    return value


def _nonnegative(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise NykraError(f"{field} must be a finite, non-negative number")
    return float(value)


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise NykraError("score must be a finite number")
    return float(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStore:
    def __init__(self, home: Path | str | None = None):
        self.home = Path(home) if home is not None else default_home()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.home / "history.sqlite3"
        self._initialize()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.database), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._db() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, SCHEMA_VERSION):
                raise NykraError(f"Unsupported history schema {version}; expected {SCHEMA_VERSION}")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    evaluator_id TEXT NOT NULL,
                    objective TEXT NOT NULL CHECK(objective IN ('maximize','minimize')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    parent_id TEXT,
                    status TEXT NOT NULL CHECK(status IN ('ok','failed','invalid')),
                    score REAL,
                    cost_units REAL NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    snapshot_ref TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attempts_run ON attempts(run_id, created_at);
                CREATE TABLE IF NOT EXISTS activity (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    task_id TEXT,
                    tool TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK(outcome IN ('succeeded','failed','cancelled','denied')),
                    duration_ms REAL NOT NULL,
                    observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_activity_task ON activity(source, task_id, observed_at);
            """)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def token(self) -> str:
        """Automatically provision a local service token on first use."""
        path = self.home / "auth.token"
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            new_token = secrets.token_urlsafe(32)
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                fd = os.open(path, flags, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(new_token)
                return new_token
            except FileExistsError:
                return path.read_text(encoding="utf-8").strip()

    def authorize(self, received: str) -> bool:
        return hmac.compare_digest(self.token(), received)

    def create_run(self, *, task: str, agent: str, evaluator_id: str,
                   objective: str = "maximize", run_id: str | None = None) -> dict[str, Any]:
        task = _required_text(task, "task", 8192)
        agent = _required_text(agent, "agent", 256)
        evaluator_id = _required_text(evaluator_id, "evaluator_id", 256)
        if objective not in ("maximize", "minimize"):
            raise NykraError("objective must be maximize or minimize")
        run_id = _required_text(run_id, "run_id", 256) if run_id is not None else uuid.uuid4().hex
        result = dict(id=run_id, task=task, agent=agent, evaluator_id=evaluator_id,
                      objective=objective, created_at=_now())
        with self._db() as conn:
            try:
                conn.execute(
                    "INSERT INTO runs(id, task, agent, evaluator_id, objective, created_at) "
                    "VALUES(:id,:task,:agent,:evaluator_id,:objective,:created_at)", result)
            except sqlite3.IntegrityError as exc:
                raise NykraError(f"run_id already exists: {run_id}") from exc
        return result

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise NykraError(f"unknown run_id: {run_id}")
        return dict(row)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or not (1 <= limit <= 1000):
            raise NykraError("limit must be between 1 and 1000")
        with self._db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def record_attempt(self, *, run_id: str, parent_id: str | None = None,
                       status: str = "ok", score: float | None = None,
                       cost_units: float = 1.0, elapsed_ms: float = 0.0,
                       snapshot_ref: str | None = None, metadata: dict[str, Any] | None = None,
                       attempt_id: str | None = None) -> dict[str, Any]:
        run_id = _required_text(run_id, "run_id", 256)
        if parent_id is not None:
            parent_id = _required_text(parent_id, "parent_id", 256)
        if status not in ("ok", "failed", "invalid"):
            raise NykraError("status must be ok, failed, or invalid")
        if status == "ok" and score is None:
            raise NykraError("a successful attempt must provide an evaluated score")
        score = _score(score) if score is not None else None
        cost_units = _nonnegative(cost_units, "cost_units")
        elapsed_ms = _nonnegative(elapsed_ms, "elapsed_ms")
        if snapshot_ref is not None:
            snapshot_ref = _required_text(snapshot_ref, "snapshot_ref", 1024)
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise NykraError("metadata must be a JSON object")
        try:
            metadata_json = json.dumps(metadata, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise NykraError("metadata must be valid finite JSON") from exc
        if len(metadata_json) > 32768:
            raise NykraError("metadata exceeds 32 KiB; store large artifacts externally")
        attempt_id = _required_text(attempt_id, "attempt_id", 256) if attempt_id else uuid.uuid4().hex
        if attempt_id == parent_id:
            raise NykraError("an attempt cannot parent itself")
        result = dict(id=attempt_id, run_id=run_id, parent_id=parent_id,
                      status=status, score=score, cost_units=cost_units,
                      elapsed_ms=elapsed_ms, snapshot_ref=snapshot_ref,
                      metadata_json=metadata_json, created_at=_now())
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone() is None:
                raise NykraError(f"unknown run_id: {run_id}")
            if parent_id is not None:
                parent = conn.execute("SELECT run_id FROM attempts WHERE id=?", (parent_id,)).fetchone()
                if parent is None or parent["run_id"] != run_id:
                    raise NykraError("parent_id must refer to an earlier attempt in the same run")
            try:
                conn.execute("""
                    INSERT INTO attempts (id,run_id,parent_id,status,score,cost_units,
                                          elapsed_ms,snapshot_ref,metadata_json,created_at)
                    VALUES (:id,:run_id,:parent_id,:status,:score,:cost_units,
                            :elapsed_ms,:snapshot_ref,:metadata_json,:created_at)
                """, result)
            except sqlite3.IntegrityError as exc:
                raise NykraError(f"attempt_id already exists: {attempt_id}") from exc
        result["metadata"] = metadata
        del result["metadata_json"]
        return result

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self._db() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM attempts WHERE run_id=? ORDER BY rowid", (run_id,))]
        for row in rows:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        return rows

    def record_activity(self, *, source: str, tool: str, outcome: str,
                        duration_ms: float, task_id: str | None = None,
                        event_id: str | None = None) -> dict[str, Any]:
        """Store structured tool outcomes only; never persist tool arguments or outputs."""
        source = _identifier(source, "source", 128)
        tool = _identifier(tool, "tool")
        if task_id is not None:
            task_id = _identifier(task_id, "task_id")
        if outcome not in ("succeeded", "failed", "cancelled", "denied"):
            raise NykraError("outcome must be succeeded, failed, cancelled, or denied")
        duration_ms = _nonnegative(duration_ms, "duration_ms")
        event_id = _identifier(event_id, "event_id") if event_id is not None else uuid.uuid4().hex
        payload = dict(event_id=event_id, source=source, tool=tool, outcome=outcome,
                       duration_ms=duration_ms, task_id=task_id, observed_at=_now())
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """INSERT OR IGNORE INTO activity
                   (event_id, source, task_id, tool, outcome, duration_ms, observed_at)
                   VALUES (:event_id,:source,:task_id,:tool,:outcome,:duration_ms,:observed_at)""",
                payload)
            inserted = cursor.rowcount == 1
            if not inserted:
                existing = dict(conn.execute(
                    "SELECT * FROM activity WHERE event_id=?", (event_id,)).fetchone())
                fields = ("source", "task_id", "tool", "outcome", "duration_ms")
                if any(existing[key] != payload[key] for key in fields):
                    raise NykraError("event_id already belongs to a different observation")
                payload["observed_at"] = existing["observed_at"]
        return {**payload, "inserted": inserted, "kind": "tool_observation",
                "scored_attempt": False}

    def list_activity(self, *, source: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise NykraError("limit must be between 1 and 1000")
        with self._db() as conn:
            if source is None:
                rows = conn.execute("SELECT * FROM activity ORDER BY rowid DESC LIMIT ?", (limit,))
            else:
                rows = conn.execute(
                    "SELECT * FROM activity WHERE source=? ORDER BY rowid DESC LIMIT ?",
                    (_identifier(source, "source", 128), limit))
            return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self._db() as conn:
            runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            activity = conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
            ide_events = conn.execute("SELECT COUNT(*) FROM activity WHERE source LIKE 'ide-%'").fetchone()[0]
        return {"schema_version": SCHEMA_VERSION, "run_count": runs,
                "attempt_count": attempts, "activity_count": activity, "ide_activity_count": ide_events,
                "database": str(self.database)}
