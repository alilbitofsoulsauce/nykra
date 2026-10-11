"""Per-user, fail-open workstation runtime for passive, local agent observation.

This is not an operating-system kernel service. It is a cooperative, single-instance
background process with an explicit consent-based autostart option.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import __version__
from .relai_history import RelaiHistoryObserver, default_relai_database
from .ide_inbox import drain_ide_inbox
from .store import HistoryStore, NykraError, default_home

HEARTBEAT_STALE_SECONDS = 15.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".nykra-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        # On Windows, a concurrent short-lived reader can temporarily hold
        # a sharing lock that rejects an otherwise valid atomic replacement.
        # Retry only that transient error; preserve atomicity and fail after a
        # small bounded delay for genuine permission problems.
        for retry in range(8):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if retry == 7:
                    raise
                time.sleep(0.02 * (retry + 1))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def _single_instance(path: Path) -> Iterator[None]:
    """Kernel-owned advisory lock, independent of PID files and PID recycling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise NykraError("Nykra workstation runtime is already running") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise NykraError("Nykra workstation runtime is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _health_file(home: Path) -> Path:
    return home / "runtime-health.json"


def _stop_file(home: Path) -> Path:
    return home / "runtime-stop.json"


def read_health(home: Path | str | None = None) -> dict:
    root = Path(home).expanduser().resolve() if home is not None else default_home()
    try:
        record = json.loads(_health_file(root).read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("invalid health")
    except (FileNotFoundError, ValueError, OSError):
        return {"state": "not_running", "healthy": False, "version": __version__}
    stamp = record.get("heartbeat_epoch")
    recent = isinstance(stamp, (int, float)) and 0 <= time.time() - stamp < HEARTBEAT_STALE_SECONDS
    if not recent and record.get("state") not in ("stopped", "not_running"):
        record["state"] = "stale"
    record["healthy"] = bool(recent and record.get("state") in ("observing", "waiting_for_relai"))
    record.pop("heartbeat_epoch", None)
    # A path-like error or a persisted prompt is never returned in health output.
    return record


def assert_not_running(home: Path | str | None = None) -> None:
    """Check the OS lock, not just a stale heartbeat, before replacing runtime files."""
    root = Path(home).expanduser().resolve() if home is not None else default_home()
    with _single_instance(root / "runtime.lock"):
        pass


def request_stop(home: Path | str | None = None, *, timeout: float = 8.0) -> dict:
    root = Path(home).expanduser().resolve() if home is not None else default_home()
    health = read_health(root)
    if not health.get("healthy"):
        return {"stopped": True, "reason": "not_running", "health": health}
    instance = health.get("instance")
    if not isinstance(instance, str) or not instance:
        raise NykraError("Cannot safely identify the Nykra instance to stop")
    _atomic_json(_stop_file(root), {"instance": instance})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_health(root)
        if current.get("state") in ("stopped", "stale", "not_running"):
            return {"stopped": True, "health": current}
        if current.get("instance") != instance:
            return {"stopped": True, "reason": "instance_changed", "health": current}
        time.sleep(0.1)
    return {"stopped": False, "reason": "timeout", "health": read_health(root)}


def run_runtime(home: Path | str | None = None, *, interval: float = 2.0,
                source_db: Path | str | None = None, cycles: int | None = None) -> dict:
    """Run cooperatively; never starts an MCP server, hooks other apps or captures prompts.

    cycles is a deterministic bounded test mode; production runs until stop requested.
    """
    if not (0.25 <= interval <= 120.0):
        raise NykraError("interval must be between 0.25 and 120 seconds")
    if cycles is not None and (isinstance(cycles, bool) or not 1 <= cycles <= 10000):
        raise NykraError("cycles must be 1..10000")
    root = Path(home).expanduser().resolve() if home is not None else default_home()
    root.mkdir(parents=True, exist_ok=True)
    with _single_instance(root / "runtime.lock"):
        instance = uuid.uuid4().hex
        # Ignore stale stop signals from a previously completed runtime.
        _stop_file(root).unlink(missing_ok=True)
        store = HistoryStore(root)
        source = Path(source_db).expanduser().resolve() if source_db else default_relai_database().resolve()
        observer = None
        state = {
            "version": __version__,
            "instance": instance,
            "pid": os.getpid(),
            "started_at": _utc(),
            "state": "waiting_for_relai",
            "observer": "read_only_relai_history",
            "source_detected": False,
            "observation_count": 0,
            "ide_events_ingested": 0,
            "ide_events_rejected": 0,
            "last_issue": None,
        }

        def publish(status: str) -> None:
            state["state"] = status
            state["heartbeat_at"] = _utc()
            state["heartbeat_epoch"] = time.time()
            _atomic_json(_health_file(root), state)

        publish("waiting_for_relai")
        count = 0
        try:
            while cycles is None or count < cycles:
                count += 1
                try:
                    stop_message = json.loads(_stop_file(root).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    stop_message = None
                if isinstance(stop_message, dict) and stop_message.get("instance") == instance:
                    break
                try:
                    inbox = drain_ide_inbox(store)
                    state["ide_events_ingested"] += inbox["ingested"]
                    state["ide_events_rejected"] += inbox["rejected"]
                    state["observation_count"] = store.stats()["activity_count"]
                except (OSError, sqlite3.Error, NykraError):
                    # IDE observation is always best-effort; never stop the runtime.
                    state["ide_last_issue"] = "inbox_unavailable"
                if not source.is_file():
                    observer = None
                    state["source_detected"] = False
                    state["last_issue"] = None
                    publish("waiting_for_relai")
                else:
                    state["source_detected"] = True
                    try:
                        if observer is None:
                            observer = RelaiHistoryObserver(store, source)
                            observer.baseline()  # never silently backfill history
                        report = observer.poll()
                        state["observation_count"] = store.stats()["activity_count"]
                        state["last_issue"] = None
                        state["poll_count"] = count
                        state["recorded_in_session"] = report["recorded"]
                        publish("observing")
                    except (NykraError, sqlite3.Error, OSError):
                        observer = None
                        state["last_issue"] = "source_read_unavailable"
                        publish("waiting_for_relai")
                if cycles is None or count < cycles:
                    time.sleep(interval)
        finally:
            _stop_file(root).unlink(missing_ok=True)
            publish("stopped")
        return {"state": "stopped", "cycles": count, "source_detected": state["source_detected"]}
