"""Read-only live Rel.AI history adapter.

Uses JSON projections from a known Rel.AI state database; never SELECTs the raw
event payload and never modifies the Rel.AI database. This is a compatibility
adapter, distinct from the low-latency host subscription.
"""
from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import closing

from .store import HistoryStore, NykraError

_REQUIRED_COLUMNS = {
    "task_id", "event_key", "task_updated_at_ms", "event_timestamp", "payload",
}
_ALLOWED = {"succeeded", "failed", "cancelled", "blocked"}
_SQL = """
SELECT task_id, event_key, task_updated_at_ms, event_timestamp,
       json_extract(payload, '$.tool.name') AS tool,
       json_extract(payload, '$.status') AS status,
       json_extract(payload, '$.durationMs') AS duration_ms
FROM task_history_events
WHERE task_updated_at_ms >= ?
  AND json_valid(payload)
  AND json_extract(payload, '$.status') IN ('succeeded', 'failed', 'cancelled', 'blocked')
  AND json_type(payload, '$.durationMs') IN ('integer', 'real')
ORDER BY task_updated_at_ms, task_id, event_index
LIMIT ?
"""


def default_relai_database() -> Path:
    state = os.environ.get("REL_AI_MCP_STATE_DIR")
    return Path(state).expanduser() / "durable-state.sqlite" if state else Path.home() / ".rel-ai-mcp" / "durable-state.sqlite"


class RelaiHistoryObserver:
    def __init__(self, store: HistoryStore, database: Path | str | None = None,
                 *, overlap_ms: int = 3000, max_events: int = 2000):
        self.store = store
        self.database = Path(database).expanduser().resolve() if database else default_relai_database().resolve()
        if not 0 <= overlap_ms <= 60000:
            raise NykraError("overlap_ms must be 0..60000")
        if not 1 <= max_events <= 10000:
            raise NykraError("max_events must be 1..10000")
        self.overlap_ms = overlap_ms
        self.max_events = max_events
        self.watermark: int | None = None
        self.start_bound = 0
        self.started_after: datetime | None = None
        self.counters = {"recorded": 0, "duplicates": 0, "invalid": 0, "read": 0}

    def _connect(self) -> sqlite3.Connection:
        if not self.database.is_file():
            raise NykraError("Rel.AI state database not found; is a supported Rel.AI host installed?")
        conn = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON")
            cols = {row[1] for row in conn.execute("PRAGMA table_info(task_history_events)")}
            if not _REQUIRED_COLUMNS.issubset(cols) or "event_index" not in cols:
                raise NykraError("Incompatible Rel.AI task_history_events schema")
            return conn
        except BaseException:
            conn.close()
            raise

    def baseline(self) -> int:
        """Default start at current timestamp, so no historical data is imported."""
        self.started_after = datetime.now(timezone.utc)
        with closing(self._connect()) as conn:
            newest = conn.execute("SELECT COALESCE(MAX(task_updated_at_ms),0) FROM task_history_events").fetchone()[0]
        self.watermark = max(0, int(newest) + 1)
        self.start_bound = self.watermark
        return self.watermark

    def poll(self, *, backfill: bool = False) -> dict[str, Any]:
        if self.watermark is None:
            if not backfill:
                self.baseline()
                return self.report()
            self.watermark = 0
            self.start_bound = 0
            self.started_after = None
        with closing(self._connect()) as conn:
            rows = list(conn.execute(_SQL, (max(self.start_bound, self.watermark - self.overlap_ms), self.max_events)))
        for task, event_key, updated, event_timestamp, tool, status, elapsed in rows:
            self.counters["read"] += 1
            # Database rewrites old event rows on task updates, so a watermark
            # alone is insufficient to enforce future-only observation.
            if self.started_after is not None:
                try:
                    observed = datetime.fromisoformat(str(event_timestamp).replace("Z", "+00:00"))
                    if observed.tzinfo is None:
                        raise ValueError("missing timezone")
                    if observed.astimezone(timezone.utc) < self.started_after:
                        continue
                except (TypeError, ValueError):
                    self.counters["invalid"] += 1
                    continue
            # SQL extracts whitelisted scalars, not raw payload, prompts or output.
            if not isinstance(task, str) or not task or not isinstance(event_key, str) or not event_key:
                self.counters["invalid"] += 1
                continue
            if not isinstance(tool, str) or not tool or status not in _ALLOWED or isinstance(elapsed, bool):
                self.counters["invalid"] += 1
                continue
            try:
                duration = float(elapsed)
            except (TypeError, ValueError):
                self.counters["invalid"] += 1
                continue
            if not math.isfinite(duration) or duration < 0:
                self.counters["invalid"] += 1
                continue
            unique = hashlib.sha256((str(self.database) + "\0" + task + "\0" + event_key).encode()).hexdigest()
            try:
                outcome = "denied" if status == "blocked" else status
                saved = self.store.record_activity(
                    source="relai-history", tool=tool, task_id=task,
                    outcome=outcome, duration_ms=duration,
                    event_id="relai-db-" + unique[:40],
                )
                self.counters["recorded" if saved["inserted"] else "duplicates"] += 1
            except NykraError:
                self.counters["invalid"] += 1
        if rows:
            # Overlap gives recent history time to settle; event IDs are stable.
            self.watermark = max(self.watermark, max(int(row[2]) for row in rows) + 1)
        return self.report()

    def report(self) -> dict[str, Any]:
        return {"source": "relai-history", "mode": "read-only",
                "raw_payloads_retrieved": False, "backfill_default": False,
                "future_only": self.started_after is not None,
                "watermark_ms": self.watermark, **self.counters}

    def watch(self, *, poll_seconds: float = 2.0, resume: bool = False) -> None:
        if not 0.2 <= poll_seconds <= 120:
            raise NykraError("poll interval must be 0.2..120 seconds")
        if not resume or self.watermark is None:
            self.baseline()
        try:
            while True:
                self.poll()
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            return
