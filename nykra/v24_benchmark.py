"""Frozen v0.24 independent-agent-session real Git+Docker cold/warm replay.

Existing genuine Codex-generated source is replayed; no new inference is
invoked. Three distinct sessions per task/mode deliberately vary policy and
feedback settings. The cache key is content/evaluator based, not a prompt or
parent history key. Full final hidden checks run separately for all passes.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

from . import agent_workflow as wf
from . import public_cache_v24 as cache
from .v20_grader import EVIDENCE, ROOT
from .v21_grader import manifest

PROTOCOL = EVIDENCE / "v24_protocol.json"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen():
    raw=PROTOCOL.read_bytes()
    config=json.loads(raw)
    _,protocol_sha=manifest()
    if config["id"]!="nykra-v24-independent-session-content-cache-v1":
        raise ValueError("unexpected experiment")
    if config["evaluator_sha256"]!=protocol_sha:
        raise ValueError("public evaluator input protocol changed")
    if [x["id"] for x in config["cases"]] != ["youtube-dl-27","youtube-dl-43"]:
        raise ValueError("unregistered tasks")
    return config,hashlib.sha256(raw).hexdigest()


def source_for(task):
    state_file=ROOT/task["reference_source_state"]
    if (state_file.parent.parent.parent.resolve() != EVIDENCE.resolve()
            or _sha(state_file)!=task["reference_source_state_sha256"]):
        raise ValueError("archived original model-source provenance mismatch")
    state=json.loads(state_file.read_bytes())
    attempts=[x for x in state["attempts"] if x["id"]==task["reference_attempt_id"]]
    if len(attempts)!=1:
        raise ValueError("original model attempt unavailable")
    src=attempts[0]["source"]
    if hashlib.sha256(src.encode("utf-8")).hexdigest()!=task["source_sha256"]:
        raise ValueError("original candidate source changed")
    if attempts[0]["public"]["passed"]!=task["historical_public_pass"]:
        raise ValueError("original public grade disagrees")
    return src


def condition(task,source,mode):
    if mode not in ("cold","cached"):
        raise ValueError("unknown condition")
    sessions=[]
    started=time.monotonic()
    cache_folder=ROOT/"experiments"/"v24-benchmark-cache"/task["id"]
    # Every cached condition starts from an empty namespace. Control cold
    # mode never reads or writes this cache. No removal of existing data:
    # refusing reused namespace makes the measurement immutable.
    if mode=="cached" and cache_folder.exists():
        raise ValueError("benchmark cache namespace is not fresh")
    if mode=="cached":
        cache_folder.mkdir(parents=True)
    with patch.object(cache,"CACHE_ROOT",cache_folder):
        for i, config in enumerate(task["independent_sessions"]):
            req=wf.start(task_id=task["id"],policy=config["policy"],
                         budget=1,enriched_feedback=config["enriched_feedback"],
                         driver="relai-supervised",approve=True)
            submit=wf.submit(req["session_id"],source,approve=True,
                             cache_public=(mode=="cached"),
                             agent_label="archived-original-source-no-new-inference")
            done=wf.finalize(req["session_id"],approve=True)
            events=done["ancestry"]
            if len(events)!=1 or events[0]["status"]!=submit["evaluated"]["public"]["status"]:
                raise ValueError("session public ancestry changed")
            if done["full_success"]!=task["historical_public_pass"]:
                raise ValueError("independent hidden verifier disagrees with frozen public history")
            sessions.append({
                "session_id":req["session_id"],
                "policy":config["policy"],
                "enriched_feedback":config["enriched_feedback"],
                "public_status":submit["evaluated"]["public"]["status"],
                "public_passed":submit["evaluated"]["public"]["passed"],
                "public_cache_hit":submit["evaluated"]["public_cache_hit"],
                "public_cache_key":submit["evaluated"]["public_cache_key"],
                "git_apply_calls":done["actual_git_apply_calls"],
                "public_docker_calls":done["actual_public_evaluator_calls"],
                "hidden_status":done["final_hidden"]["status"],
                "full_success":done["full_success"],
                "patch_sha256":submit["evaluated"]["patch_sha256"],
                "source_sha256":submit["evaluated"]["source_sha256"],
            })
    return {
        "mode":mode,"wall_seconds":round(time.monotonic()-started,4),
        "new_model_inference_calls":0,
        "sessions":sessions,
        "git_apply_calls":sum(x["git_apply_calls"] for x in sessions),
        "public_docker_calls":sum(x["public_docker_calls"] for x in sessions),
        "cache_hits":sum(x["public_cache_hit"] for x in sessions),
        "hidden_verified_passes":sum(x["full_success"] for x in sessions),
    }


def run_case(task_id,*,approve=False):
    if approve is not True:raise ValueError("explicit local Git/Docker authorization required")
    protocol,sha=frozen()
    task=next((t for t in protocol["cases"] if t["id"]==task_id),None)
    if task is None:raise ValueError("unregistered")
    source=source_for(task)
    output=EVIDENCE/("v24_cache_"+task_id.replace("-","_")+".json")
    if output.exists():raise ValueError("refuse overwrite")
    result={
        "schema":"nykra-v24-independent-session-cold-warm-real-docker-v1",
        "protocol_sha256":sha,"task_id":task_id,
        "model_source_sha256":hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "new_model_calls":0,"status":"running","conditions":{},
    }
    for mode in task["condition_order"]:
        result["conditions"][mode]=condition(task,source,mode)
        output.with_suffix(".partial").write_text(json.dumps(result,indent=2)+"\n")
    cold, cached=result["conditions"]["cold"],result["conditions"]["cached"]
    for a,b in zip(cold["sessions"],cached["sessions"]):
        if any(a[k]!=b[k] for k in ("source_sha256","patch_sha256","public_status",
                                    "public_passed","hidden_status","full_success")):
            raise ValueError("cached result altered model source or independent grader outcome")
    if cold["public_docker_calls"]!=len(task["independent_sessions"]) or cached["public_docker_calls"]!=1:
        raise ValueError("cache failed to eliminate duplicate real public tests")
    result["status"]="completed"
    output.write_text(json.dumps(result,indent=2)+"\n")
    output.with_suffix(".partial").unlink(missing_ok=True)
    return result
