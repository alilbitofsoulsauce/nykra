"""Example of a LOCAL harness reporting its own evaluated exploration evidence.

Run 'python -m nykra serve' first, then 'python -m examples.bridge_client'.
No model API, external network connection, or real agent runtime is required.
"""

import json
import os
from urllib.request import Request, urlopen

from nykra.store import HistoryStore

HOST = os.environ.get("NYKRA_ENDPOINT", "http://127.0.0.1:8765")
store = HistoryStore()


def post(path, payload):
    request = Request(
        HOST + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + store.token(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


run = post("/v1/runs", {
    "task": "Synthetic instrumented task",
    "agent": "example-local-bridge",
    "evaluator_id": "fixture-v1",
    "objective": "maximize",
})
first = post("/v1/attempts", {"run_id": run["id"], "score": 1.0})
second = post("/v1/attempts", {
    "run_id": run["id"], "parent_id": first["id"], "score": 1.5,
})
result = post("/v1/replay", {"run_id": run["id"], "policy": "adaptive", "budget": 2})
print(json.dumps({
    "note": "Demonstration data only, not experimental evidence",
    "run_id": run["id"], "attempt_id": second["id"],
    "best_replayed_score": result["best_score"],
}, indent=2))
