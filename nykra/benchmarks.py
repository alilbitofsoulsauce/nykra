"""Reproducible paired *reference-search* benchmark with honest evidence gates.

Both policies visit exactly the same pre-generated grid tasks independently,
with the same worker, evaluator, expansion budget and wall-time cap. Differences
are from search policy, NOT model quality. Paired results are descriptive:
this is not a coding-agent / LLM improvement study.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import deque
from typing import Any

from .agent_host import SubprocessSearchHost, evaluate_grid
from .store import NykraError

BENCHMARK_ID = "grid-paired-prospective-v1"
BASELINE = "breadth"
CHALLENGER = "adaptive"
FIXED_SEED = 20261011
DEFAULT_BUDGET = 12
DEFAULT_COUNT = 48
GRID_SIZE = 5


def _has_path(board: dict) -> bool:
    walls = {tuple(w) for w in board["walls"]}
    start = tuple(board["start"])
    goal = tuple(board["goal"])
    q = deque([start])
    seen = {start}
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            return True
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt = (x+dx, y+dy)
            if (0<=nxt[0]<board["width"] and 0<=nxt[1]<board["height"]
                    and nxt not in walls and nxt not in seen):
                seen.add(nxt)
                q.append(nxt)
    return False


def generate_tasks(*, count:int = DEFAULT_COUNT, seed:int = FIXED_SEED) -> list[dict]:
    if type(count) is not int or not 20 <= count <= 120:
        raise NykraError("paired benchmark requires 20..120 tasks")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise NykraError("seed must be a 32-bit unsigned integer")
    rng = random.Random(seed)
    boards=[]
    fingerprints=set()
    proposals=0
    while len(boards)<count:
        proposals+=1
        if proposals>10000:
            raise NykraError("unable to generate distinct solvable benchmark tasks")
        start=[rng.randrange(GRID_SIZE),rng.randrange(GRID_SIZE)]
        goal=[rng.randrange(GRID_SIZE),rng.randrange(GRID_SIZE)]
        distance=abs(start[0]-goal[0])+abs(start[1]-goal[1])
        if not 2<=distance<=8:
            continue
        wall_probability=(0.04,0.12,0.20)[len(boards)%3]
        walls=[[x,y] for x in range(GRID_SIZE) for y in range(GRID_SIZE)
               if [x,y] not in (start,goal) and rng.random()<wall_probability]
        board={"width":GRID_SIZE,"height":GRID_SIZE,
               "start":start,"goal":goal,"walls":walls}
        blob=json.dumps(board,sort_keys=True,separators=(",",":"))
        stamp=hashlib.sha256(blob.encode()).hexdigest()
        if stamp in fingerprints or not _has_path(board):
            continue
        fingerprints.add(stamp)
        boards.append(board)
    return boards


def _exact_discordance_test(improved: int, regressed: int) -> float:
    """One-sided exact McNemar/binomial tail for matched binary outcomes."""
    n = improved+regressed
    if n==0:
        return 1.0
    return math.fsum(math.comb(n,k)/2**n for k in range(improved,n+1))


def _bootstrap_interval(deltas:list[int], *, seed:int, reps:int=4000)->list[float]:
    if not deltas:
        raise NykraError("cannot calculate CI on an empty benchmark")
    rng = random.Random(seed^0x5F3759DF)
    length=len(deltas)
    means=[]
    for _ in range(reps):
        means.append(sum(deltas[rng.randrange(length)] for j in range(length))/length)
    means.sort()
    return [round(means[int(reps*0.025)],5),
            round(means[min(reps-1,int(reps*0.975))],5)]


def paired_reference_benchmark(*, count:int=DEFAULT_COUNT,
                               budget:int=DEFAULT_BUDGET,
                               seed:int=FIXED_SEED,
                               approval:bool=False) -> dict[str,Any]:
    if approval is not True:
        raise NykraError("explicit approval required before subprocess benchmarking")
    if type(budget) is not int or not 3<=budget<=60:
        raise NykraError("attempt budget must be between 3 and 60")
    tasks=generate_tasks(count=count,seed=seed)
    # Predefine one evaluator, two policies, a fixed per-task time cap.
    host=SubprocessSearchHost()
    outcomes=[]
    for board in tasks:
        arms={}
        for policy in (BASELINE,CHALLENGER):
            # Each policy gets a fresh frontier and a fresh subprocess per expansion.
            try:
                answer=host.execute(policy,board,max_attempts=budget,seconds=12)
                score=evaluate_grid(board,answer.candidate).score
                arms[policy]={"passed":score==1.0,
                              "attempts_used":answer.attempts_used,
                              "status":"ok"}
            except Exception:
                # A failed arm remains in the denominator; no rerun advantage.
                arms[policy]={"passed":False,"attempts_used":budget,"status":"failed"}
        outcomes.append(arms)
    successes={name:sum(row[name]["passed"] for row in outcomes)
               for name in (BASELINE,CHALLENGER)}
    n=len(outcomes)
    better=sum(row[CHALLENGER]["passed"] and not row[BASELINE]["passed"] for row in outcomes)
    worse=sum(row[BASELINE]["passed"] and not row[CHALLENGER]["passed"] for row in outcomes)
    both=sum(row[BASELINE]["passed"] and row[CHALLENGER]["passed"] for row in outcomes)
    neither=n-better-worse-both
    differences=[int(row[CHALLENGER]["passed"])-int(row[BASELINE]["passed"])
                 for row in outcomes]
    p=_exact_discordance_test(better,worse)
    failure={name:sum(row[name]["status"]=="failed" for row in outcomes)
             for name in (BASELINE,CHALLENGER)}
    means={name:round(sum(row[name]["attempts_used"] for row in outcomes)/n,3)
           for name in (BASELINE,CHALLENGER)}
    fingerprint=hashlib.sha256(json.dumps(tasks,sort_keys=True).encode()).hexdigest()
    return {
        "benchmark_id":BENCHMARK_ID,
        "source_of_tasks":"reproducible_pseudorandom_solvable_grids",
        "sample":n,
        "seed":seed,
        "task_manifest_sha256":fingerprint,
        "attempt_budget_per_arm":budget,
        "seconds_budget_per_task_arm":12,
        "baseline":BASELINE,
        "challenger":CHALLENGER,
        "results":{
            "baseline_successes":successes[BASELINE],
            "challenger_successes":successes[CHALLENGER],
            "baseline_success_rate":round(successes[BASELINE]/n,5),
            "challenger_success_rate":round(successes[CHALLENGER]/n,5),
            "difference_percentage_points":round(100*(successes[CHALLENGER]-successes[BASELINE])/n,3),
            "difference_95_bootstrap_interval_percentage_points":[round(100*x,2) for x in _bootstrap_interval(differences,seed=seed)],
            "paired_one_sided_exact_p":p,  # retain small nonzero exact probabilities
            "challenger_only_succeeds":better,
            "baseline_only_succeeds":worse,
            "both_succeed":both,
            "neither_succeeds":neither,
            "mean_actual_expansions":means,
            "execution_failures":failure,
        },
        "limits":{
            "agent":"deterministic_grid_reference_worker; NOT a language model",
            "task_scope":"generated 5x5 solvable mazes; not programming tasks",
            "policy_scope":"adaptive selects lower Manhattan heuristic; this benchmark may favor that heuristic",
            "statistical_scope":"paired exact test and task bootstrap conditional on the specified procedural task generator; exploratory single seed; not an independent real-agent replication",
            "causal_claim":"only comparative performance of these two algorithms on this particular reference task generator",
            "general_agent_improvement_proven":False,
            "recursive_self_improvement_proven":False,
        },
        "qualification":"Results come from running both real search algorithms on the same new grid tasks under equal expansion caps, not replaying stored scores. No LLM was used.",
    }
