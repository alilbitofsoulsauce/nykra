"""Pre-registered task-level v0.20 replicated fork outcomes, no pseudoreplication."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from .v20_grader import EVIDENCE,ROOT,manifest

NAMES={"youtube-dl-3":"v20_youtube_dl_3.json",
       "youtube-dl-5":"v20_youtube_dl_5.json",
       "youtube-dl-23":"v20_youtube_dl_23.json",
       "tqdm-1":"v20_tqdm_1.json"}

def sha(path:Path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit():
    p,locked=manifest()
    pre=EVIDENCE/"v20_prevalidation.json"
    eligibility=json.loads(pre.read_bytes())
    if eligibility["protocol_sha256"]!=locked:
        raise ValueError("preflight provenance mismatch")
    if [v["id"] for v in eligibility["tasks"]] != [t["id"] for t in p["tasks"]]:
        raise ValueError("registered tasks differ")
    outcomes=[]
    forks=[]
    for task in p["tasks"]:
        path=EVIDENCE/NAMES[task["id"]]
        raw=json.loads(path.read_bytes())
        if raw["protocol_sha256"]!=locked or raw["task_id"]!=task["id"]:
            raise ValueError("raw evidence provenance mismatch")
        row={"id":task["id"],"project":task["project"],
             "status":raw["status"],"reason":raw["shared_prefix_reason"],
             "raw_path":path.relative_to(ROOT).as_posix(),"raw_sha256":sha(path),
             "common_attempts":len(raw["shared_prefix"]),
             "model_setup_or_patch_failures":sum(
                 a["public"]["status"] in ("setup_error","invalid_patch")
                 for a in raw["shared_prefix"]),
             "model_syntax_invalid_count":sum(
                 a["public"].get("error_type")=="SyntaxError"
                 for a in raw["shared_prefix"])}
        if raw["status"]=="completed":
            if raw["shared_prefix_reason"]!="three_public_failures":
                raise ValueError("nonfailed prefix compared")
            if raw["fork_actions"]!={"baseline":{"kind":"revise","parent_attempt_id":"attempt-3"},
                                    "nykra":{"kind":"new_root","parent_attempt_id":None}}:
                raise ValueError("not an actual fork")
            draws=raw["draws"]
            if len(draws)!=4 or sorted((x["draw"],x["arm"]) for x in draws)!=[
                (1,"baseline"),(1,"nykra"),(2,"baseline"),(2,"nykra")]:
                raise ValueError("missing repeated paired model draws")
            digest=hashlib.sha256(json.dumps(raw["shared_prefix"],sort_keys=True).encode()).hexdigest()
            if any(x["common_prefix_sha256"]!=digest for x in draws):
                raise ValueError("arms did not share identical serialized history")
            row["fork"]=True
            row["results"]={}
            for arm in ("baseline","nykra"):
                matched=[x for x in draws if x["arm"]==arm]
                for x in matched:
                    if x["hidden"] is None:
                        raise ValueError("hidden verification not finished")
                    if x["full_success"] and (not x["attempt"]["public"]["passed"]
                                              or not x["hidden"]["passed"]):
                        raise ValueError("invalid claimed success")
                row["results"][arm]={
                    "draws":len(matched),
                    "public_passes":sum(x["attempt"]["public"]["passed"] is True
                                        for x in matched),
                    "hidden_verified_passes":sum(x["full_success"] for x in matched),
                    "any_hidden_pass":any(x["full_success"] for x in matched),
                    "reported_tokens":sum(x["attempt"]["tokens_reported"] or 0
                                           for x in matched),
                    "missing_token_counters":sum(x["attempt"]["tokens_reported"] is None
                                                  for x in matched),
                    "tokens_over_soft_cap":sum(x["soft_token_limit_exceeded"]
                                               for x in matched),
                }
            forks.append(row)
        elif raw["status"]!="not_forkable":
            raise ValueError("unfinished task")
        outcomes.append(row)
    prefix_file=EVIDENCE/"v20_shared_prefix_hidden.json"
    audit=json.loads(prefix_file.read_bytes())
    if audit["protocol_sha256"]!=locked or not audit["not_disclosed_to_any_model_call"]:
        raise ValueError("post-inference shared hidden check provenance mismatch")
    shared_ids={x["id"] for x in outcomes if x["reason"]=="public_solved"}
    if {x["task_id"] for x in audit["cases"]}!=shared_ids:
        raise ValueError("unverified early solutions")
    for case in audit["cases"]:
        matching=next(x for x in outcomes if x["id"]==case["task_id"])
        if case["raw_task_sha256"]!=matching["raw_sha256"]:
            raise ValueError("early-success source changed")
    fork_stats={
        arm:{
            "task_successes":sum(x["results"][arm]["any_hidden_pass"] for x in forks),
            "sample_successes":sum(x["results"][arm]["hidden_verified_passes"] for x in forks),
            "sample_calls":sum(x["results"][arm]["draws"] for x in forks),
            "reported_tokens":sum(x["results"][arm]["reported_tokens"] for x in forks),
        } for arm in ("baseline","nykra")
    }
    return {"schema":"nykra-v20-cross-project-repeated-fork-summary-v1",
            "protocol_sha256":locked,"registered":len(outcomes),
            "prevalidated_eligible":sum(x["eligible"] for x in eligibility["tasks"]),
            "task_statuses":{x["id"]:x["status"] for x in outcomes},
            "genuine_forked_tasks":len(forks),
            "repeated_draws_per_arm_per_fork":p["fork_draws_per_arm"],
            "shared_prefix_public_solutions":len(shared_ids),
            "shared_prefix_posthoc_hidden_successes":sum(x["hidden"]["passed"]
                                                            for x in audit["cases"]),
            "invalid_prefixes":sum(x["reason"]=="infrastructure_or_invalid"
                                    for x in outcomes),
            "observed_by_policy":fork_stats,
            "hidden_audit_sha256":sha(prefix_file),
            "prevalidation_sha256":sha(pre),
            "not_independent_samples":True,
            "general_causal_improvement_proven":False,
            "official_bugsinpy_harness":False,
            "official_swebench":False,
            "statistical_sign_test":"not applicable with zero discordant issue outcomes",
            "limitations":"n=4 issues, 2 actual forks; repeated model responses per issue correlated; one early common pass and one invalid candidate prevented forks; historical training contamination unknown; no hard per-call token cap; restricted one-function repair; Docker not certified malicious-code isolation.",
            "tasks":outcomes,
            }

def save():
    path=EVIDENCE/"v20_summary.json"
    if path.exists():
        raise ValueError("will not overwrite result")
    result=audit()
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return path
