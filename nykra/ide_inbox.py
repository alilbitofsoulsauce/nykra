"""Privacy-minimized IDE spool ingestion.

The editor extension emits allowlisted metadata to per-user local atomic files.
The local Nykra runtime handles those files without exposing a network service.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .store import HistoryStore, NykraError

ALLOWED_KEYS = frozenset({"event_id", "source", "task_id", "tool", "outcome", "duration_ms"})
IDE_SOURCE = re.compile(r"^ide-(?:vscode|cursor|windsurf|vscodium|vscode-compatible)$")
WORKSPACE_ID = re.compile(r"^ws-[0-9a-f]{24}$")
EVENT_ID = re.compile(r"^ide-[0-9a-f-]{36}$")
ALLOWED_TOOLS = {"document_save", "task_completed"}
MAX_EVENT_BYTES = 2048


def drain_ide_inbox(store: HistoryStore, *, limit: int = 250) -> dict[str, int]:
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise NykraError("invalid inbox batch size")
    inbox = store.home / "ide-inbox"
    result = {"ingested": 0, "duplicates": 0, "rejected": 0, "pending": 0}
    if not inbox.is_dir() or inbox.is_symlink():
        return result
    entries = sorted((p for p in inbox.iterdir() if p.name.endswith(".json")), key=lambda p: p.name)
    result["pending"] = max(0, len(entries) - limit)
    for entry in entries[:limit]:
        if entry.is_symlink() or not entry.is_file():
            result["rejected"] += 1
            # Leave symlinks untouched, never follow links out of this directory.
            continue
        try:
            if entry.stat().st_size > MAX_EVENT_BYTES:
                raise ValueError("oversized event")
            message = json.loads(entry.read_text(encoding="utf-8"))
            if not isinstance(message, dict) or set(message) != ALLOWED_KEYS:
                raise ValueError("unexpected fields")
            if (not isinstance(message["source"], str) or not IDE_SOURCE.fullmatch(message["source"])
                or not isinstance(message["task_id"], str) or not WORKSPACE_ID.fullmatch(message["task_id"])
                or not isinstance(message["event_id"], str) or not EVENT_ID.fullmatch(message["event_id"])
                or message["tool"] not in ALLOWED_TOOLS
                or message["outcome"] not in ("succeeded", "failed")):
                raise ValueError("untrusted event values")
            saved = store.record_activity(**message)
            result["ingested" if saved["inserted"] else "duplicates"] += 1
        except (ValueError, UnicodeError, OSError, TypeError, NykraError):
            result["rejected"] += 1
        finally:
            # Delete only regular, non-symlink files within this owned inbox.
            try:
                if entry.is_file() and not entry.is_symlink():
                    entry.unlink(missing_ok=True)
            except OSError:
                pass
    return result
