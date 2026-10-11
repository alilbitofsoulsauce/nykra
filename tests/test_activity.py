import sqlite3
import tempfile
import unittest
from pathlib import Path

from nykra import SCHEMA_VERSION
from nykra.store import HistoryStore, NykraError


class ActivityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(self.temp.name)

    def test_activity_is_not_an_evaluated_candidate(self):
        event = self.store.record_activity(
            source="relai", tool="relai_exec", task_id="task-123",
            outcome="succeeded", duration_ms=125.5, event_id="relai-op123")
        self.assertTrue(event["inserted"])
        self.assertFalse(event["scored_attempt"])
        self.assertEqual(self.store.stats()["activity_count"], 1)
        self.assertEqual(self.store.stats()["attempt_count"], 0)
        self.assertEqual(self.store.list_activity()[0]["tool"], "relai_exec")

    def test_duplicate_retry_is_idempotent_and_conflict_rejected(self):
        kwargs = {"source": "relai", "tool": "relai_exec", "outcome": "failed",
                  "duration_ms": 25, "event_id": "stable-id"}
        first = self.store.record_activity(**kwargs)
        repeated = self.store.record_activity(**kwargs)
        self.assertTrue(first["inserted"])
        self.assertFalse(repeated["inserted"])
        self.assertEqual(self.store.stats()["activity_count"], 1)
        with self.assertRaises(NykraError):
            self.store.record_activity(**{**kwargs, "outcome": "succeeded"})

    def test_invalid_identifiers_and_durations(self):
        valid = dict(source="relai", tool="relai_exec", outcome="succeeded", duration_ms=1)
        for key, value in (("source", "bad\nnewline"), ("tool", "cmd --secret=123"),
                           ("outcome", "unknown"), ("duration_ms", -1),
                           ("duration_ms", float("nan"))):
            with self.subTest(key=key, value=value), self.assertRaises(NykraError):
                self.store.record_activity(**{**valid, key: value})
        with self.assertRaises(NykraError):
            self.store.record_activity(**{**valid, "task_id": "secret prompt contents"})
        with self.assertRaises(NykraError):
            self.store.list_activity(limit=0)

    def test_v1_database_upgrades_without_erasing_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE runs(id TEXT PRIMARY KEY, task TEXT, agent TEXT, evaluator_id TEXT, objective TEXT, created_at TEXT)")
                conn.execute("CREATE TABLE attempts(id TEXT PRIMARY KEY, run_id TEXT, parent_id TEXT, status TEXT, score REAL, cost_units REAL, elapsed_ms REAL, snapshot_ref TEXT, metadata_json TEXT, created_at TEXT)")
                conn.execute("INSERT INTO runs VALUES ('old-run','task','agent','v1','maximize','2026')")
                conn.execute("PRAGMA user_version = 1")
                conn.commit()
            finally:
                conn.close()
            migrated = HistoryStore(directory)
            self.assertEqual(migrated.get_run("old-run")["task"], "task")
            self.assertEqual(migrated.stats()["schema_version"], SCHEMA_VERSION)
            migrated.record_activity(source="relai", tool="relai_read",
                                     outcome="succeeded", duration_ms=1)
            self.assertEqual(migrated.stats()["activity_count"], 1)


if __name__ == "__main__":
    unittest.main()
