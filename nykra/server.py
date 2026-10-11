"""Loopback-only JSON ingestion API for explicitly integrated execution harnesses."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from typing import Any

from . import __version__
from .replay import replay
from .store import HistoryStore, NykraError

MAX_BODY = 1024 * 1024


def make_handler(store: HistoryStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Nykra/" + __version__

        def _reply(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            # Prevent cross-origin browser pages from driving this local API.
            if self.headers.get("Origin") is not None:
                self._reply(403, {"error": "browser-origin requests are not permitted"})
                return False
            provided = self.headers.get("Authorization", "")
            if not provided.startswith("Bearer ") or not store.authorize(provided[7:]):
                self._reply(401, {"error": "local authentication required"})
                return False
            return True

        def do_GET(self) -> None:
            if self.path == "/health":
                self._reply(200, {"status": "ok", "service": "nykra", "version": __version__})
                return
            if not self._authorized():
                return
            url = urlsplit(self.path)
            if url.path == "/v1/status" and not url.query:
                self._reply(200, store.stats())
            elif url.path == "/v1/activity":
                try:
                    values = parse_qs(url.query, strict_parsing=True)
                    if set(values) - {"limit", "source"}:
                        raise NykraError("unsupported query parameter")
                    limit = int(values["limit"][0]) if "limit" in values else 100
                    source = values["source"][0] if "source" in values else None
                    self._reply(200, {"events": store.list_activity(source=source, limit=limit)})
                except (NykraError, ValueError) as exc:
                    self._reply(400, {"error": str(exc)})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            if self.path not in ("/v1/runs", "/v1/attempts", "/v1/replay", "/v1/activity"):
                self._reply(404, {"error": "not found"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                self._reply(415, {"error": "Content-Type must be application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self._reply(411, {"error": "valid Content-Length required"})
                return
            if length > MAX_BODY:
                self._reply(413, {"error": "request too large"})
                return
            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise NykraError("request body must be a JSON object")
                if self.path == "/v1/runs":
                    result = store.create_run(**payload)
                    status = 201
                elif self.path == "/v1/attempts":
                    result = store.record_attempt(**payload)
                    status = 201
                elif self.path == "/v1/activity":
                    result = store.record_activity(**payload)
                    status = 201 if result["inserted"] else 200
                else:
                    result = replay(store, **payload)
                    status = 200
                self._reply(status, result)
            except (json.JSONDecodeError, NykraError, TypeError, ValueError) as exc:
                self._reply(400, {"error": str(exc)})
            except Exception:
                # Do not leak stack traces, workstation paths, or internal details.
                self._reply(500, {"error": "internal service error"})

        def do_OPTIONS(self) -> None:
            self._reply(403, {"error": "browser-origin requests are not permitted"})

        def log_message(self, format: str, *args: Any) -> None:
            # No payloads or authentication headers are logged.
            return

    return Handler


def create_server(store: HistoryStore, port: int = 8765) -> ThreadingHTTPServer:
    if not isinstance(port, int) or not (0 <= port <= 65535):
        raise NykraError("port must be between 0 and 65535")
    # Intentionally never bind publicly accessible interfaces.
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))
