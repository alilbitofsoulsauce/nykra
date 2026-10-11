"""Strict, task-level, non-pooled v0.21 evidence audit."""
from __future__ import annotations
import hashlib,json
from math import comb
from pathlib import Path
from .v21_grader import EVIDENCE,ROOT,manifest

def sha(path:Path):return hashlib.sha256(path.read_bytes()).hexdigest()

def _exact_p(positive,negative):
    n=positive+negative
    if not n:return None
    return min(1.,2*sum(comb(n,k) for k in range(min(positive,negative)+1))/2**n)

def audit():
    config,protocol_sha=manifest()
    pre=EVIDENCE/"v21_prevalidation.json"
    doc=json.loads(pre.read_bytes())
    if doc["protocol_sha256"]!=protocol_sha:
        raise ValueError("eligibility protocol not frozen")
    if [x["id"] for x in config["tasks"]] != [x["id"] for x in doc["tasks"]]:
        raise ValueError("task list differs")
    rows=[]
    pairs=[]
    shared=[]
    exclusions=[]
    for task in config["tasks"]:
        path=EVIDENCE/("v21_"+task["id"].replace("-","_")+".json")
        raw=json.loads(path.read_bytes())
        if raw["protocol_sha256"]!=protocol_sha or raw["task_id"]!=task["id"]:
            raise ValueError("task evidence mismatch")
        eligible=next(x["eligible"] for x in doc["tasks"] if x["id"]==task["id"])
        if raw["eligible"]!=eligible:
            raise ValueError("eligibility conflict")
        item={"id":task["id"],"status":raw["status"],
              "eligible":eligible,"raw_path":path.relative_to(ROOT).as_posix(),
              "raw_sha256":sha(path)}
        if not eligible:
            if raw["status"]!="preflight_excluded" or raw["arms"]:
                raise ValueError("invalid exclusion")
            exclusions.append(task["id"])
        elif raw["status"]=="shared_solved":
            if not raw["shared"]["public"]["passed"] or not raw["shared_hidden"]:
                raise ValueError("shared success lacks independent hidden grade")
            item["shared_hidden_verified"]=raw["shared_hidden"]["passed"]
            shared.append(item)
        elif raw["status"]=="completed":
            if not raw["shared"] or raw["shared"]["public"]["passed"]:
                raise ValueError("paired despite already solved")
            if raw["shared"]["public"]["status"].startswith("evaluator_"):
                raise ValueError("infrastructure error counted as repair trial")
            arms={x["arm"]:x for x in raw["arms"]}
            if len(raw["arms"])!=2 or set(arms)!={"bare","enriched"}:
                raise ValueError("incomplete paired sample")
            item["arms"]={}
            for arm in ("bare","enriched"):
                x=arms[arm]
                if x["hidden"] is None or type(x["full_success"]) is not bool:
                    raise ValueError("hidden grading incomplete")
                if x["full_success"]!=bool(x["candidate"]["public"]["passed"] and
                                           x["hidden"]["passed"]):
                    raise ValueError("false successful repair")
                item["arms"][arm]={
                    "public_pass":x["candidate"]["public"]["passed"],
                    "hidden_pass":x["hidden"]["passed"],
                    "full_success":x["full_success"],
                    "reported_tokens":x["candidate"]["tokens_reported"],
                    "model_seconds":x["candidate"]["model_seconds"],
                    "prompt_sha256":x["prompt_sha256"],
                    "model_status":x["candidate"]["model_status"]}
            if item["arms"]["bare"]["prompt_sha256"]==item["arms"]["enriched"]["prompt_sha256"]:
                raise ValueError("same prompt in both intervention arms")
            pairs.append(item)
        else:
            raise ValueError("incomplete or unexpected result "+raw["status"])
        rows.append(item)
    a=sum(x["arms"]["enriched"]["full_success"] for x in pairs)
    b=sum(x["arms"]["bare"]["full_success"] for x in pairs)
    aonly=sum(x["arms"]["enriched"]["full_success"] and
              not x["arms"]["bare"]["full_success"] for x in pairs)
    bonly=sum(x["arms"]["bare"]["full_success"] and
              not x["arms"]["enriched"]["full_success"] for x in pairs)
    return {
        "schema":"nykra-v21-actionable-public-feedback-summary-v1",
        "protocol_sha256":protocol_sha,"registered":len(rows),
        "eligible":sum(x["eligible"] for x in rows),
        "reference_exclusions":exclusions,
        "shared_first_attempt_public_solved":len(shared),
        "shared_first_attempt_hidden_verified":sum(x["shared_hidden_verified"] for x in shared),
        "valid_paired_tasks":len(pairs),
        "enriched_full_successes":a,"bare_full_successes":b,
        "enriched_only":aonly,"bare_only":bonly,
        "paired_exact_two_sided_p":_exact_p(aonly,bonly),
        "reported_revision_tokens":{
            arm:sum(x["arms"][arm]["reported_tokens"] or 0 for x in pairs)
            for arm in ("bare","enriched")},
        "model_token_counters_complete":all(
            x["arms"][arm]["reported_tokens"] is not None
            for x in pairs for arm in ("bare","enriched")),
        "not_a_policy_fork_study":True,
        "general_effectiveness_improvement_proven":False,
        "official_bugsinpy_harness":False,"official_swebench":False,
        "preflight_sha256":sha(pre),
        "task_results":rows,
        "limitations":"One model, six preregistered tasks all from youtube-dl; five eligible, only two paired, one enriched-only win and three early shared successes; historical pretraining leakage and output randomness unknown, soft token ceiling, one-function-only modifications, noncertified Docker isolation."
    }

def save():
    path=EVIDENCE/"v21_summary.json"
    if path.exists():raise ValueError("will not overwrite evidence")
    report=audit()
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return path
