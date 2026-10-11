"""Rel.AI-first AI agent turn driver for Nykra feedback sessions.

A connected model supplies one candidate per feedback cycle through existing
Rel.AI MCP tools; this module does NOT invoke an LLM independently. Bounded
candidate source files are temporarily cached locally to allow automatic
finalization and revisions; cache code is cleared when session terminates.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .coding_worker import validate_source
from .iterative import IterativeCoding
from .store import HistoryStore, NykraError
from .workstation import _single_instance

SOURCE_LIMIT = 4500
CACHE_MARKER = "nykra-relai-agent-v1"
TRUST_NOTE = (
    "Rel.AI is an execution/transport host. A connected AI agent must author "
    "each candidate; no local model inference is available."
)


def _atomic_write(path: Path, content: str) -> None:
    if not isinstance(content, str) or not content or len(content.encode("utf-8")) > SOURCE_LIMIT:
        raise NykraError("candidate source is empty or too large")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".nykra-", dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RelaiAgent:
    def __init__(self, store: HistoryStore):
        self.store = store
        self.loop = IterativeCoding(store)
        self.cache_root = store.home / "relai-agent-cache"

    @staticmethod
    def _uuid(value: str) -> str:
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
            raise NykraError("Rel.AI session/attempt ID must be a generated hexadecimal identifier")
        return value

    def _folder(self, session_id: str) -> Path:
        return self.cache_root / self._uuid(session_id)

    def _require_owned(self, session_id: str) -> Path:
        folder = self._folder(session_id)
        if not folder.is_dir() or folder.is_symlink():
            raise NykraError("session has no managed Rel.AI cache; use a relai-agent session")
        marker = folder / "OWNER"
        if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding="ascii") != CACHE_MARKER:
            raise NykraError("unrecognized Rel.AI cache; refusing access")
        return folder

    @staticmethod
    def _source_file(folder: Path, attempt_id: str) -> Path:
        return folder / (RelaiAgent._uuid(attempt_id) + ".py")

    @staticmethod
    def _clear_source(folder: Path) -> None:
        for entry in folder.iterdir():
            if entry.is_symlink():
                raise NykraError("unsafe managed cache symlink")
        for entry in folder.glob("*.py"):
            entry.unlink(missing_ok=True)

    def start(self, *, task_id: str, policy: str = "depth", budget: int = 4,
              max_seconds: float = 1200, threshold: float = 1.0,
              trial_id: str | None = None, task_key: str | None = None,
              approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required to start a Rel.AI agent session")
        result = self.loop.start(task_id=task_id, policy=policy, budget=budget,
                                 max_seconds=max_seconds, threshold=threshold,
                                 trial_id=trial_id, task_key=task_key, approval=True)
        folder = self._folder(result["session_id"])
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        _atomic_write(folder / "OWNER", CACHE_MARKER)
        return self.next(result["session_id"])

    def next(self, session_id: str) -> dict:
        status = self.loop.status(session_id)
        if status["state"] != "active":
            return {"session": status, "agent_required": False, "model_invocation": False,
                    "instruction": "Session is finished or aborted."}
        folder = self._require_owned(session_id)
        request = status["request"]
        parent_source = None
        if request and request["parent_attempt_id"] is not None:
            file = self._source_file(folder, request["parent_attempt_id"])
            try:
                parent_source = file.read_text(encoding="utf-8")
            except OSError:
                raise NykraError("revision parent source is missing") from None
            if len(parent_source.encode("utf-8")) > SOURCE_LIMIT:
                raise NykraError("cached source exceeds size limit")
        return {
            "session": status,
            "transport": "relai",
            "agent_required": request is not None,
            "model_invocation": False,
            "source_cache": "local, temporary; sources deleted on finish/abort",
            "request": request,
            "parent_source": parent_source,
            "instruction": (
                "Author ONE complete Python solve(...) function and write it as a UTF-8 "
                "file in the authorized workspace. Follow the task description, selected "
                "parent (when revising), and public training failure examples. Do not "
                "use imports, attribute access, file IO, network calls or privileged tools. "
                "Submit with python -m nykra relai-agent submit --session SESSION_ID "
                "--candidate-file FILE --approve, then repeat until finished. "
                "Held-out tests are available only after finalization."
                if request else "No attempts remain. Use relai-agent finalize --approve."
            ),
            "qualification": TRUST_NOTE,
        }

    def submit(self, session_id: str, *, source: str, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required before running candidate code")
        try:
            validate_source(source)
        except (ValueError, SyntaxError):
            raise NykraError("invalid restricted candidate source") from None
        folder = self._require_owned(session_id)
        with _single_instance(folder / "cycle.lock"):
            status = self.loop.status(session_id)
            if status["state"] != "active" or status["request"] is None:
                raise NykraError("session is no longer accepting candidates")
            staged = folder / "current-pending.py"
            _atomic_write(staged, source)
            try:
                evaluated = self.loop.submit(session_id, source=source, approval=True)
                os.replace(staged, self._source_file(folder, evaluated["evaluated_attempt_id"]))
            finally:
                staged.unlink(missing_ok=True)
            if evaluated["request"] is not None:
                return {"state": "awaiting_agent", "evaluated": evaluated,
                        "next": self.next(session_id)}
            return self._finalize_locked(session_id, folder, evaluated)

    def _finalize_locked(self, session_id: str, folder: Path,
                         latest: dict | None = None) -> dict:
        status = self.loop.status(session_id)
        if status["state"] != "active":
            raise NykraError("cannot finalize an inactive session")
        if status["request"] is not None:
            raise NykraError("additional attempts remain; submit or abort")
        if status["best_attempt_id"] is None:
            raise NykraError("session contains no evaluated candidates")
        sourcefile = self._source_file(folder, status["best_attempt_id"])
        try:
            best_source = sourcefile.read_text(encoding="utf-8")
        except OSError:
            raise NykraError("best candidate source missing from cache") from None
        finished = self.loop.finish(session_id, best_source=best_source, approval=True)
        self._clear_source(folder)
        return {
            "state": "finished", "session": finished, "last_evaluation": latest,
            "heldout_score": finished["final_score"],
            "attempts_used": finished["evaluations_used"],
            "source_cache_cleared": True, "model_invocation": False,
            "qualification": TRUST_NOTE,
        }

    def finalize(self, session_id: str, *, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required for held-out evaluation")
        folder = self._require_owned(session_id)
        with _single_instance(folder / "cycle.lock"):
            return self._finalize_locked(session_id, folder)

    def abort(self, session_id: str, *, approval: bool = False) -> dict:
        if approval is not True:
            raise NykraError("explicit approval required for abort")
        folder = self._require_owned(session_id)
        with _single_instance(folder / "cycle.lock"):
            stopped = self.loop.abort(session_id, approval=True)
            self._clear_source(folder)
        return {"state": "aborted", "session": stopped, "source_cache_cleared": True}
