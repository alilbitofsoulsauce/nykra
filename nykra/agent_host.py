"""Policy-controllable agent execution host for bounded grid-search benchmarks.

The reference worker is a real independent subprocess producing newly expanded
candidate states under a host-selected breadth/depth/adaptive policy. The host
selects the frontier, validates moves and enforces budgets; a separate trusted
evaluator checks final results. The reference worker is NOT an LLM and this
module does NOT hook into opaque Rel.AI/Cursor agent internals.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .evaluation import EvaluatorResult
from .prospective import ExecutionResult, ProspectiveExperiment
from .replay import POLICIES
from .store import NykraError, _nonnegative

MAX_GRID_CELLS = 256
MAX_INPUT_BYTES = 16384
MAX_OUTPUT_BYTES = 16384


def validate_grid(task: dict) -> dict:
    if not isinstance(task, dict) or set(task) != {"width","height","walls","start","goal"}:
        raise NykraError("grid task requires width, height, walls, start and goal")
    width, height = task["width"], task["height"]
    if (isinstance(width, bool) or not isinstance(width, int) or
        isinstance(height, bool) or not isinstance(height, int) or
        not 2 <= width <= 16 or not 2 <= height <= 16 or width*height > MAX_GRID_CELLS):
        raise NykraError("grid dimensions are outside bounded limits")
    def pos(raw: Any) -> tuple[int,int]:
        if (not isinstance(raw, list) or len(raw) != 2 or
            any(isinstance(v, bool) or not isinstance(v, int) for v in raw)):
            raise NykraError("grid positions must be pairs of integers")
        x,y = raw
        if not (0 <= x < width and 0 <= y < height):
            raise NykraError("grid position outside bounds")
        return x,y
    start, goal = pos(task["start"]), pos(task["goal"])
    if not isinstance(task["walls"], list) or len(task["walls"]) > width*height:
        raise NykraError("invalid grid wall list")
    walls = {pos(value) for value in task["walls"]}
    if len(walls) != len(task["walls"]) or start in walls or goal in walls:
        raise NykraError("duplicate walls or blocked endpoints")
    if start == goal:
        raise NykraError("start and goal must differ for an exploration task")
    return {"width":width, "height":height,
            "walls": [list(xy) for xy in sorted(walls)],
            "start":list(start), "goal":list(goal)}


def evaluate_grid(task: dict, candidate: Any) -> EvaluatorResult:
    """Independent, rule-based verifier; does not use agent's heuristic."""
    board = validate_grid(task)
    if not isinstance(candidate, list) or len(candidate) > MAX_GRID_CELLS:
        return EvaluatorResult(score=0.0, cost_units=0)
    try:
        nodes = [tuple(n) for n in candidate]
    except (TypeError, ValueError):
        return EvaluatorResult(score=0.0, cost_units=0)
    walls = {tuple(w) for w in board["walls"]}
    good = bool(nodes and nodes[0] == tuple(board["start"]) and
                all(len(n)==2 and all(isinstance(v,int) and not isinstance(v,bool) for v in n)
                    and 0 <= n[0] < board["width"] and 0 <= n[1] < board["height"]
                    and n not in walls for n in nodes) and
                all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for a,b in zip(nodes,nodes[1:])) and
                nodes[-1] == tuple(board["goal"]))
    return EvaluatorResult(score=1.0 if good else 0.0, cost_units=0)


@dataclass(frozen=True)
class SearchRecord:
    path: tuple[tuple[int,int], ...]
    heuristic: float
    order: int


class SubprocessSearchHost:
    """Launch trusted JSON worker; host retains frontier decisions and scoring.

    subprocess is not a security sandbox. Only explicitly authorized, trusted
    worker argv should be supplied; no shell, workspace cwd, or inherited secrets.
    """
    def __init__(self, worker_argv: Sequence[str] | None = None,
                 *, per_call_seconds: float = 3.0):
        if not 0.1 <= per_call_seconds <= 30:
            raise NykraError("worker per-call timeout must be 0.1..30 seconds")
        if worker_argv is None:
            self.argv = [sys.executable, str(Path(__file__).with_name("reference_agent.py").resolve())]
            self.agent_kind = "nykra-reference-process-no-llm"
        else:
            if (not isinstance(worker_argv, (list,tuple)) or not 1 <= len(worker_argv) <= 20 or
                any(not isinstance(arg,str) or not arg or "\x00" in arg for arg in worker_argv)):
                raise NykraError("worker executable and arguments must be explicit trusted strings")
            self.argv = list(worker_argv)
            self.agent_kind = "externally_supplied_trusted_process"
        self.per_call_seconds = float(per_call_seconds)
        self.last_trace: list[tuple[int,int]] = []

    @staticmethod
    def _trusted_env() -> dict:
        # Do not send API keys or inherited credentials to subprocess workers.
        env = {}
        for k in ("SYSTEMROOT","WINDIR","PATH","TEMP","TMP","TMPDIR"):
            if k in os.environ:
                env[k] = os.environ[k]
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _expand(self, board: dict, path: tuple[tuple[int,int], ...], seconds: float) -> list[SearchRecord]:
        request = json.dumps({"task":board,"path":[list(p) for p in path]}, separators=(",",":"))
        if len(request.encode("utf-8")) > MAX_INPUT_BYTES:
            raise NykraError("agent request exceeds maximum input size")
        with tempfile.TemporaryDirectory(prefix="nykra-worker-") as tmp:
            # Stdout is capped after the child exits; trusted executable must
            # obey output bounds. stderr is deliberately not captured.
            try:
                proc = subprocess.run(
                    self.argv, input=request, capture_output=True,
                    text=True, encoding="utf-8", errors="strict",
                    cwd=tmp, env=self._trusted_env(),
                    timeout=min(seconds, self.per_call_seconds), check=False)
            except (subprocess.TimeoutExpired, OSError, UnicodeError):
                raise NykraError("trusted agent process timed out or could not run") from None
        if proc.returncode != 0 or len(proc.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise NykraError("trusted agent process failed or exceeded response size")
        try:
            output = json.loads(proc.stdout)
        except (ValueError, TypeError):
            raise NykraError("agent returned malformed JSON") from None
        if not isinstance(output,dict) or set(output)!={"children"} or not isinstance(output["children"],list) or len(output["children"])>4:
            raise NykraError("agent response must contain at most four children")
        options: list[SearchRecord] = []
        seen: set[tuple[int,int]] = set()
        blocked = {tuple(n) for n in board["walls"]}
        for i, child in enumerate(output["children"]):
            if not isinstance(child,dict) or set(child)!={"path","heuristic"}:
                raise NykraError("agent supplied unsupported candidate fields")
            raw = child["path"]
            try:
                proposed = tuple(tuple(p) for p in raw)
            except (TypeError,ValueError):
                raise NykraError("agent supplied an invalid candidate path") from None
            if (len(proposed)!=len(path)+1 or proposed[:-1]!=path or
                any(len(p)!=2 or any(type(v) is not int for v in p) for p in proposed)):
                raise NykraError("agent may only extend the current path by one step")
            x,y=proposed[-1]
            px,py=path[-1]
            if (not 0<=x<board["width"] or not 0<=y<board["height"] or
                (x,y) in blocked or (x,y) in path or abs(x-px)+abs(y-py)!=1 or
                (x,y) in seen):
                raise NykraError("agent returned illegal or duplicate state")
            seen.add((x,y))
            hint=child["heuristic"]
            if (type(hint) not in (int,float) or not math.isfinite(hint) or
                not 0<=hint<=MAX_GRID_CELLS):
                raise NykraError("invalid agent heuristic")
            options.append(SearchRecord(proposed,float(hint),i))
        return options

    def execute(self, policy: str, task: dict, max_attempts: int,
                seconds: float) -> ExecutionResult:
        if policy not in POLICIES:
            raise NykraError("unknown exploration policy")
        if type(max_attempts) is not int or not 1<=max_attempts<=1000:
            raise NykraError("invalid attempt budget")
        _nonnegative(seconds,"seconds")
        if seconds<=0:
            raise NykraError("time budget must be positive")
        board=validate_grid(task)
        beginning=time.monotonic()
        initial=tuple(board["start"])
        goal=tuple(board["goal"])
        frontier=[SearchRecord((initial,), abs(initial[0]-goal[0])+abs(initial[1]-goal[1]),0)]
        visited:set[tuple[int,int]]=set()
        trace=[]
        attempts=0
        best=frontier[0]
        order=1
        while frontier and attempts<max_attempts:
            left=seconds-(time.monotonic()-beginning)
            if left<=0:
                raise NykraError("host time budget elapsed")
            if policy=="breadth":
                frontier.sort(key=lambda n:(len(n.path),n.order))
            elif policy=="depth":
                frontier.sort(key=lambda n:(-len(n.path),n.order))
            else:
                frontier.sort(key=lambda n:(n.heuristic,n.order))
            item=frontier.pop(0)
            position=item.path[-1]
            if position in visited:
                continue
            visited.add(position)
            trace.append(position)
            attempts+=1
            if item.heuristic<best.heuristic:
                best=item
            if position==goal:
                best=item
                break
            if attempts>=max_attempts:
                break
            new=self._expand(board,item.path,left)
            for branch in new:
                if branch.path[-1] in visited:
                    continue
                frontier.append(SearchRecord(branch.path,branch.heuristic,order))
                order+=1
        self.last_trace=trace
        return ExecutionResult(candidate=[list(p) for p in best.path],
                               attempts_used=attempts, cost_units=float(attempts))


def run_reference_benchmark(*, count:int=60, budget:int=12, approval:bool=False,
                            seed:int=73) -> dict:
    """Run independent subprocess search on fixed generated tasks in a temp trial.

    Scores result from the independent path verifier. Any statistical signal
    applies to the deterministic reference worker, NOT to real AI assistants.
    """
    import random
    from .store import HistoryStore
    if approval is not True:
        raise NykraError("explicit approval required to run benchmark subprocesses")
    if type(count) is not int or not 40<=count<=200:
        raise NykraError("benchmark task count must be 40..200")
    if type(budget) is not int or not 2<=budget<=128:
        raise NykraError("benchmark attempt budget must be 2..128")
    rng=random.Random(seed)
    host=SubprocessSearchHost()
    with tempfile.TemporaryDirectory(prefix="nykra-host-benchmark-") as td:
        experiment=ProspectiveExperiment(HistoryStore(td))
        trial=experiment.create(evaluator_id="reference-grid-verifier-v1",
                               objective="maximize",threshold=1,
                               challenger="adaptive",attempt_budget=budget,
                               seconds_budget=20,max_tasks=count,min_per_arm=10,
                               approval=True)
        first_traces={}
        for i in range(count):
            # Tasks generated before assignment, with independent grid verifier.
            width,height=6,6
            blocks=[[x,y] for x in range(width) for y in range(height)
                    if (x,y) not in ((0,0),(width-1,height-1)) and rng.random()<0.13]
            task={"width":width,"height":height,"start":[0,0],
                  "goal":[width-1,height-1],"walls":blocks}
            identifier=f"reference-grid-task-{i:03}"
            outcome=experiment.run_task(
                trial_id=trial["id"],task_key=identifier,task=task,
                execute=host.execute,evaluate=evaluate_grid,approval=True)
            if i<4:
                first_traces[identifier]={"state":outcome["status"],
                                          "visited_digest":hashlib.sha256(
                                            repr(host.last_trace).encode()).hexdigest()[:16],
                                          "expansions":len(host.last_trace)}
        experiment.close(trial["id"])
        report=experiment.report(trial["id"])
        return {"agent":"nykra-reference-subprocess-search-agent-no-llm",
                "tasks":count,"budget":budget,
                "evidence":"new candidates generated at runtime and independently verified",
                "caveat":"Reference algorithmic agent only; not a real model or third-party AI agent.",
                "sample_trace_summaries":first_traces,"report":report}
