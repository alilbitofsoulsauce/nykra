"""Rel.AI-mediated, human-approved coding-agent experiment adapter.

ChatGPT (or another connected agent) creates candidate source proposals, Rel.AI
executes this supervisor, and Nykra selects which proposals are tested under the
assigned policy. Independent tests grade real Python code in a subprocess.

This does not introspect a model or automatically steer closed-source agents.
Never execute untrusted Python as if this were a security sandbox.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .coding_worker import validate_source
from .evaluation import EvaluatorResult
from .prospective import ExecutionResult, ProspectiveExperiment
from .replay import _rank
from .store import HistoryStore, NykraError
from .study_tasks import TASKS as STUDY_TASKS, cases as study_cases

PROTOCOL_VERSION="relai-coding-v1"
EVALUATOR_ID="nykra-coding-fixtures-v1"
_TASKS={
    "unique-sorted":"Implement solve(values) returning unique integers in ascending order.",
    "balanced-brackets":"Implement solve(text) returning whether (), [] and {} are balanced; ignore other characters.",
    "merge-intervals":"Implement solve(intervals) returning sorted merged closed intervals as lists; touching endpoints overlap.",
}
_TASKS.update(STUDY_TASKS)
_IDENT=re.compile(r"[a-z][a-z0-9-]{0,31}\Z")


def available_tasks() -> dict[str,str]:
    return dict(_TASKS)


def _cases(task_id: str, *, heldout: bool) -> list[tuple[list,Any]]:
    if task_id not in _TASKS:
        raise NykraError("unknown coding fixture")
    if task_id in STUDY_TASKS:
        return study_cases(task_id, heldout=heldout)
    r=random.Random(("heldout-" if heldout else "training-")+task_id)
    result=[]
    for i in range(32 if heldout else 18):
        if task_id=="unique-sorted":
            values=[r.randrange(-30,31) for _ in range(r.randrange(0,16))]
            if i==0:values=[]
            if i==1:values=[2,2,1,2,1]
            result.append(([values],sorted(set(values))))
        elif task_id=="balanced-brackets":
            if i==0:s=""
            elif i==1:s="([{}])"
            elif i==2:s="([)]"
            elif i==3:s="ignore words (a[b]{c})"
            else:s="".join(r.choices(list("()[]{}ab "),k=r.randrange(0,20)))
            opened=[]
            matches={")":"(","]":"[","}":"{"}
            good=True
            for ch in s:
                if ch in "([{":opened.append(ch)
                elif ch in ")]}":
                    if not opened or opened.pop()!=matches[ch]:
                        good=False
                        break
            result.append(([s],bool(good and not opened)))
        else:
            intervals=[]
            for _ in range(r.randrange(0,10)):
                a=r.randrange(-20,21);intervals.append([a,a+r.randrange(0,9)])
            if i==0:intervals=[]
            if i==1:intervals=[[1,3],[2,6],[8,10],[10,15]]
            merged=[]
            for start,end in sorted(intervals):
                if not merged or start>merged[-1][1]:
                    merged.append([start,end])
                else:
                    merged[-1][1]=max(merged[-1][1],end)
            result.append(([intervals],merged))
    return result


def _validate_pool(payload: dict) -> tuple[str,list[dict]]:
    if not isinstance(payload,dict) or set(payload)!={"task_id","proposals"}:
        raise NykraError("candidate pool must contain task_id and proposals")
    task_id=payload["task_id"]
    if task_id not in _TASKS:
        raise NykraError("unknown coding task")
    proposals=payload["proposals"]
    if not isinstance(proposals,list) or not 2<=len(proposals)<=16:
        raise NykraError("candidate pool must contain 2..16 proposals")
    seen=set()
    depths={}
    for p in proposals:
        if not isinstance(p,dict) or set(p)!={"id","parent_id","source"}:
            raise NykraError("candidate proposal must include id, parent_id, source")
        name=p["id"]
        parent=p["parent_id"]
        if not isinstance(name,str) or not _IDENT.fullmatch(name) or name in seen:
            raise NykraError("invalid or duplicate candidate ID")
        if parent is not None and (not isinstance(parent,str) or parent not in seen):
            raise NykraError("candidate parent must precede its child")
        if not isinstance(p["source"],str):
            raise NykraError("candidate source must be text")
        try:
            validate_source(p["source"])
        except (ValueError,SyntaxError):
            raise NykraError("invalid restricted candidate source") from None
        seen.add(name)
        depths[name]=0 if parent is None else depths[parent]+1
    return task_id,proposals


def _judge(task_id:str,source:str,*,heldout:bool,timeout:float=3.0)->float:
    examples=_cases(task_id,heldout=heldout)
    payload=json.dumps({"source":source,"inputs":[v[0] for v in examples]},separators=(",",":"))
    worker=Path(__file__).with_name("coding_worker.py").resolve()
    with tempfile.TemporaryDirectory(prefix="nykra-code-fixture-") as tmp:
        env={k:v for k,v in os.environ.items()
             if k in ("SYSTEMROOT","WINDIR","PATH","TEMP","TMP","TMPDIR")}
        env["PYTHONIOENCODING"]="utf-8"
        try:
            run=subprocess.run([sys.executable,"-I","-B",str(worker)],input=payload,
                               capture_output=True,text=True,encoding="utf-8",errors="replace",
                               cwd=tmp,env=env,timeout=timeout,check=False)
        except (OSError,subprocess.TimeoutExpired):
            return 0.0
    if run.returncode!=0 or len(run.stdout)>30000:
        return 0.0
    try:
        values=json.loads(run.stdout)["outputs"]
        if len(values)!=len(examples):
            return 0.0
        return sum(isinstance(actual,dict) and actual.get("value",object())==expected
                   for actual,(_,expected) in zip(values,examples))/len(examples)
    except (ValueError,TypeError,KeyError):
        return 0.0


def evaluate_source(task_id:str,source:str,*,heldout:bool=True)->float:
    """Strictly score independently generated hidden cases. Never persists source."""
    if task_id not in _TASKS:
        raise NykraError("unknown coding task")
    try:validate_source(source)
    except (ValueError,SyntaxError):
        raise NykraError("invalid candidate source") from None
    return _judge(task_id,source,heldout=heldout)


def run_proposal_trial(store:HistoryStore,*,trial_id:str,task_key:str,pool:dict,
                       approval:bool=False)->dict:
    """Rel.AI/ChatGPT proposal pool -> randomized policy -> real tests -> durable results."""
    if approval is not True:
        raise NykraError("explicit supervisor approval required before running candidate code")
    task_id,proposals=_validate_pool(pool)
    experiment=ProspectiveExperiment(store)
    registered=experiment.get(trial_id)
    if registered["evaluator_id"]!=EVALUATOR_ID or registered["objective"]!="maximize":
        raise NykraError("prospective evaluator/objective does not match coding fixtures")
    if registered["threshold"]>1 or registered["threshold"]<0:
        raise NykraError("coding evaluator requires score threshold within 0..1")
    state={"trace":[],"run_id":None,"policy":None}
    by_id={p["id"]:p for p in proposals}
    depths={}
    for p in proposals:
        depths[p["id"]]=0 if p["parent_id"] is None else depths[p["parent_id"]]+1

    def execute(policy: str, task:dict, max_attempts:int, max_seconds:float)->ExecutionResult:
        started=time.monotonic()
        run=store.create_run(task="coding-fixture-"+task_id+"-"+hashlib.sha256(task_key.encode()).hexdigest()[:16],
                             agent="explicit-agent-proposals-via-relai",evaluator_id=EVALUATOR_ID)
        state["run_id"]=run["id"]
        state["policy"]=policy
        visible={}
        stored={}
        best=None
        best_score=-1.0
        attempted=0
        order={p["id"]:i for i,p in enumerate(proposals)}
        while attempted<max_attempts:
            if time.monotonic()-started>=max_seconds:
                raise NykraError("coding experiment deadline reached")
            legal=[{"id":p["id"],"parent_id":p["parent_id"],
                    "depth":depths[p["id"]],"order":order[p["id"]]}
                   for p in proposals if p["id"] not in visible
                   and (p["parent_id"] is None or p["parent_id"] in visible)]
            if not legal:break
            chosen=_rank(legal,visible,policy,"maximize",attempted)[0]
            item=by_id[chosen["id"]]
            remaining=max_seconds-(time.monotonic()-started)
            if remaining<=0:raise NykraError("coding experiment deadline reached")
            start=time.monotonic()
            score=_judge(task_id,item["source"],heldout=False,timeout=min(3.0,remaining))
            duration=(time.monotonic()-start)*1000
            attempt=store.record_attempt(run_id=run["id"],
                                         parent_id=stored.get(item["parent_id"]),
                                         status="ok",score=score,cost_units=1.0,
                                         elapsed_ms=duration,
                                         metadata={"candidate_id":item["id"],
                                                   "source_stored":False})
            stored[item["id"]]=attempt["id"]
            visible[item["id"]]={"id":item["id"],"parent_id":item["parent_id"],
                                  "status":"ok","score":score}
            state["trace"].append({"candidate_id":item["id"],"training_score":score,
                                   "attempt_id":attempt["id"]})
            attempted+=1
            if score>best_score:
                best_score=score
                best=item["source"]
        return ExecutionResult(candidate=best,attempts_used=attempted,cost_units=float(attempted))

    def evaluate(task:dict,candidate:Any)->EvaluatorResult:
        if candidate is None:return EvaluatorResult(score=0.0,cost_units=0)
        return EvaluatorResult(score=_judge(task_id,candidate,heldout=True),cost_units=0)

    final=experiment.run_task(trial_id=trial_id,task_key=task_key,
                              task={"task_id":task_id},
                              execute=execute,evaluate=evaluate,approval=True)
    return {"protocol":PROTOCOL_VERSION,"agent_transport":"chatgpt-generated-proposals-via-relai-mcp",
            "agent_runtime_control":"external, proposal-driven; no hidden-model-policy control",
            "task_id":task_id,"policy_assigned":state["policy"],"run_id":state["run_id"],
            "attempts":state["trace"],"final_outcome":final,
            "source_persisted_in_nykra":False,
            "qualification":"A real coding task with model-authored proposals and executed tests, not autonomous LLM search control."}
