"""v0.20 genuine previously unused issue repairs with repeated controlled forks.

Four frozen BugsInPy tasks and separate hidden Docker grading. One shared
sequence of up to three Codex attempts per task. At a real 3-failure fork,
repeat the *same fourth-action prompt* twice per policy (independent inference
calls, without feeding earlier draws back into later ones). This isolates the
single depth revise versus adaptive new-root choice. Draws within one issue
are NOT statistically independent issues. Post-inference hidden evaluation
never feeds back to prompts or candidate selection.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .exploration_policy import select_next
from .repository_repair_trial import invoke_codex
from .v20_grader import EVIDENCE, grade, function_at, manifest
from .v19_fork_trial import _fork_prompt, _prefix_prompt, _steps, fork_actions

PREFLIGHT = EVIDENCE / "v20_prevalidation.json"


def validated_protocol():
    config, sha=manifest()
    if (config["shared_prefix_calls"] != 3 or
            config["fork_draws_per_arm"] != 2 or
            config["fork_budget_calls_per_sample"] != 1):
        raise ValueError("unexpected frozen comparison budgets")
    data=json.loads(PREFLIGHT.read_bytes())
    if data["protocol_sha256"] != sha:
        raise ValueError("preflight/protocol SHA mismatch")
    if [x["id"] for x in data["tasks"]] != [x["id"] for x in config["tasks"]]:
        raise ValueError("preflight task list mismatch")
    return config,sha,data


def _atomic(path:Path,data:dict):
    stage=path.with_suffix(".partial")
    stage.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(stage,path)


def _record(task, action, *, id_, request, proposer=None):
    config,_,_=validated_protocol()
    model=(proposer(request,config["max_model_seconds_per_call"]) if proposer else
           invoke_codex(request,timeout=config["max_model_seconds_per_call"]))
    source=model.get("source")
    if model.get("status")=="ok" and isinstance(source,str):
        public=grade(task,mode="public",candidate=source)
    else:
        public={"status":"model_unavailable","passed":False}
    return {"id":id_,"kind":action["kind"],
            "parent_attempt_id":action["parent_attempt_id"],
            "source":source,
            "source_sha256":hashlib.sha256(source.encode("utf-8")).hexdigest()
                            if isinstance(source,str) else None,
            "model_status":model.get("status"),
            "model_seconds":model.get("seconds"),
            "tokens_reported":model.get("tokens"),
            "public":public}


def _work(task, report, checkpoint, proposer=None):
    config,_,_=validated_protocol()
    broken=function_at(task,task["buggy_commit"])
    history=report["shared_prefix"]
    for i in range(config["shared_prefix_calls"]):
        action=select_next(policy="depth",steps=_steps(history),budget=5)
        if action is None:
            report["shared_prefix_reason"]="public_solved"
            break
        request=_prefix_prompt(task,broken,history,action)
        item=_record(task,action,id_=f"attempt-{i+1}",request=request,proposer=proposer)
        history.append(item)
        checkpoint()
        if item["public"]["status"]=="ok":
            report["shared_prefix_reason"]="public_solved"
            break
        if item["public"]["status"]!="test_failed":
            report["shared_prefix_reason"]="infrastructure_or_invalid"
            break
    if report["shared_prefix_reason"] is None:
        report["shared_prefix_reason"]="three_public_failures"
    if report["shared_prefix_reason"]!="three_public_failures":
        report["status"]="not_forkable"
        checkpoint()
        return
    actions=fork_actions(history,{"total_policy_budget":5})
    report["fork_actions"]=actions
    report["status"]="forking"
    checkpoint()
    # A draw is one independent fourth action, without prior draw outcomes
    # in its prompt. This is repeated inference, not serial policy revision.
    for draw_index in range(config["fork_draws_per_arm"]):
        for arm in task["arm_order"]:
            action=actions[arm]
            request=_fork_prompt(task,broken,history,history,action)
            item=_record(task,action,id_=f"draw-{draw_index+1}-{arm}",
                         request=request,proposer=proposer)
            report["draws"].append({
                "draw":draw_index+1,"arm":arm,
                "common_prefix_sha256":hashlib.sha256(
                    json.dumps(history,sort_keys=True).encode()).hexdigest(),
                "attempt":item,"hidden":None,
                "soft_token_limit_exceeded":isinstance(item["tokens_reported"],int)
                   and item["tokens_reported"]>config["soft_reported_tokens_per_draw"]})
            checkpoint()
    report["status"]="post_inference_hidden_scoring"
    checkpoint()
    # Freeze all public-generation records first, then inspect hidden tests
    # without revealing results to any subsequent model call.
    for draw in report["draws"]:
        candidate=draw["attempt"]
        if candidate["public"].get("passed") is True:
            hidden=grade(task,mode="hidden",candidate=candidate["source"])
        else:
            hidden={"status":"not_publicly_selected","passed":False}
        draw["hidden"]=hidden
        draw["full_success"]=candidate["public"].get("passed") is True and hidden["passed"] is True
        checkpoint()
    report["status"]="completed"
    checkpoint()


def run_task(task_id:str, output:Path, *, approve=False, proposer=None):
    if approve is not True:
        raise ValueError("explicit real model execution authorization required")
    config,sha,preflight=validated_protocol()
    task=next((x for x in config["tasks"] if x["id"]==task_id),None)
    if task is None:
        raise ValueError("unknown frozen task")
    if output.exists():
        raise ValueError("will not overwrite existing result")
    pre=next(x for x in preflight["tasks"] if x["id"]==task_id)
    output.parent.mkdir(parents=True,exist_ok=True)
    report={"schema":"nykra-v20-real-task-result-v1","task_id":task_id,
            "protocol_sha256":sha,"model":config["model"],
            "prevalidated_eligible":pre["eligible"],
            "status":"shared_prefix" if pre["eligible"] else "preflight_excluded",
            "shared_prefix":[],"shared_prefix_reason":None,
            "fork_actions":None,"draws":[]}
    def checkpoint():
        _atomic(output,report)
    checkpoint()
    if not pre["eligible"]:
        return report
    _work(task,report,checkpoint,proposer=proposer)
    return report
