import json
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nykra.server import create_server
from nykra.store import HistoryStore


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(self.temp.name)
        self.server = create_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, body=None, token=None, origin=None):
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(self.root + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method="POST" if body is not None else "GET")
        try:
            with urlopen(req, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_authenticated_ingestion_and_replay(self):
        status, health = self.request("/health")
        self.assertEqual((status, health["status"]), (200, "ok"))
        self.assertEqual(self.request("/v1/status")[0], 401)
        token = self.store.token()
        self.assertEqual(self.request("/v1/status", token=token, origin="https://evil.example")[0], 403)
        created, run = self.request("/v1/runs", {
            "task": "integration", "agent": "remote-mcp-agent", "evaluator_id": "tests-v1"}, token)
        self.assertEqual(created, 201)
        created, attempt = self.request("/v1/attempts", {
            "run_id": run["id"], "score": 0.95, "metadata": {"tests": "passed"}}, token)
        self.assertEqual(created, 201)
        self.assertEqual(attempt["score"], 0.95)
        result_code, result = self.request("/v1/replay", {
            "run_id": run["id"], "policy": "adaptive", "budget": 1}, token)
        self.assertEqual(result_code, 200)
        self.assertEqual(result["best_score"], 0.95)
        self.assertEqual(result["replayed_attempts"], 1)

    def test_activity_api_and_rejection_of_sensitive_extra_fields(self):
        token = self.store.token()
        self.assertEqual(self.request("/v1/activity")[0], 401)
        payload = {
            "source": "relai", "tool": "relai_exec", "task_id": "task-1",
            "event_id": "operation-1", "outcome": "succeeded", "duration_ms": 7.5
        }
        code, first = self.request("/v1/activity", payload, token)
        self.assertEqual((code, first["inserted"]), (201, True))
        code, duplicate = self.request("/v1/activity", payload, token)
        self.assertEqual((code, duplicate["inserted"]), (200, False))
        self.assertEqual(self.request("/v1/activity", {**payload, "raw_output": "secret"}, token)[0], 400)
        self.assertEqual(self.request("/v1/activity", {**payload, "outcome": "failed"}, token)[0], 400)
        self.assertEqual(self.request("/v1/activity", payload, token, origin="https://evil.example")[0], 403)
        code, result = self.request("/v1/activity?limit=10", token=token)
        self.assertEqual(code, 200)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(self.store.stats()["attempt_count"], 0)

    def test_invalid_requests_do_not_break_service(self):
        token = self.store.token()
        code, _ = self.request("/v1/attempts", {"run_id": "nope", "score": 2}, token)
        self.assertEqual(code, 400)
        self.assertEqual(self.request("/health")[0], 200)


if __name__ == "__main__":
    unittest.main()
