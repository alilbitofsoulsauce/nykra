import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nykra.relai_history import RelaiHistoryObserver
from nykra.store import HistoryStore, NykraError


class LiveRelaiObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "relai.sqlite"
        self.store = HistoryStore(root / "nykra")
        db = sqlite3.connect(self.source)
        try:
            db.execute("""
                CREATE TABLE task_history_events(
                    task_id TEXT, event_key TEXT, event_index INTEGER,
                    task_updated_at_ms INTEGER, event_timestamp TEXT, payload TEXT
                )
            """)
            db.commit()
        finally:
            db.close()

    def insert(self, at, event_key, *, status="succeeded", duration=10, event_time=None):
        content = {
            "eventId": event_key, "tool": {"name": "relai_exec"},
            "status": status, "durationMs": duration,
            "command": "PRIVATE_COMMAND", "stdout": "SECRET_OUTPUT",
            "prompt": "PRIVATE_PROMPT", "password": "SECRET_PASSWORD",
        }
        con = sqlite3.connect(self.source)
        try:
            con.execute(
                "INSERT INTO task_history_events VALUES(?,?,?,?,?,?)",
                ("task-1", event_key, at, at, event_time or datetime.now(timezone.utc).isoformat(), json.dumps(content)),
            )
            con.commit()
        finally:
            con.close()

    def test_future_only_does_not_import_history(self):
        self.insert(100, "old")
        observer = RelaiHistoryObserver(self.store, self.source)
        result = observer.poll()
        self.assertEqual(result["recorded"], 0)
        self.assertEqual(self.store.stats()["activity_count"], 0)
        # Simulate historical events being rewritten under a new task update.
        self.insert(101, "rewritten-old", event_time="2000-01-01T00:00:00+00:00")
        self.insert(102, "new")
        result = observer.poll()
        self.assertEqual(result["recorded"], 1)
        self.assertEqual(self.store.stats()["activity_count"], 1)
        self.assertFalse(result["raw_payloads_retrieved"])
        self.assertNotIn("PRIVATE", json.dumps(self.store.list_activity()))
        self.assertNotIn("SECRET", json.dumps(self.store.list_activity()))

    def test_backfill_duplicates_and_source_never_modified(self):
        self.insert(101, "one")
        self.insert(102, "two", status="failed")
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        observer = RelaiHistoryObserver(self.store, self.source)
        self.assertEqual(observer.poll(backfill=True)["recorded"], 2)
        self.assertEqual(observer.poll()["duplicates"], 2)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)
        self.assertEqual(
            {event["outcome"] for event in self.store.list_activity()},
            {"succeeded", "failed"})
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_incompatible_database_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "missing.sqlite"
            with self.assertRaises(NykraError):
                RelaiHistoryObserver(self.store, bad).poll()
            bad.write_text("not a SQLite database", encoding="utf-8")
            with self.assertRaises(sqlite3.DatabaseError):
                RelaiHistoryObserver(self.store, bad).poll()

    def test_bogus_score_and_raw_fields_do_not_become_evaluations(self):
        self.insert(100, "one")
        observer = RelaiHistoryObserver(self.store, self.source)
        observer.poll(backfill=True)
        self.assertEqual(self.store.stats()["run_count"], 0)
        self.assertEqual(self.store.stats()["attempt_count"], 0)


if __name__ == "__main__":
    unittest.main()
