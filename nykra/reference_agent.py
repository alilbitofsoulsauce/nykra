"""Reference agent process for Nykra's executable search-host protocol.

Run by an explicitly authorized local supervisor, not registered as an MCP tool.
One JSON request on stdin; one JSON object on stdout. No network or file access.
This is a deterministic search agent, NOT a language model.
"""
from __future__ import annotations

import json
import sys


def expand(request: dict) -> dict:
    task = request["task"]
    path = request["path"]
    width, height = task["width"], task["height"]
    goal = task["goal"]
    walls = {tuple(p) for p in task["walls"]}
    x, y = path[-1]
    # Deliberately deterministic neighbor order. Exploration policy controls
    # what the supervising search host explores next.
    children = []
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nxt = (x + dx, y + dy)
        if (not 0 <= nxt[0] < width or not 0 <= nxt[1] < height or
                nxt in walls or list(nxt) in path):
            continue
        children.append({
            "path": path + [list(nxt)],
            "heuristic": abs(goal[0]-nxt[0]) + abs(goal[1]-nxt[1]),
        })
    return {"children": children}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read(16385))
        if not isinstance(request, dict):
            raise ValueError("invalid request")
        result = expand(request)
        sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        return 0
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
        # No private input data in exception messages.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
