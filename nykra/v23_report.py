"""Independently recompute v0.23 real Docker work savings from portable proof.

This is a measured execution-work deduplication result, NOT evidence of
general code-synthesis benefit or a new model-agent success-rate improvement.
"""
from __future__ import annotations

import hashlib
import json

from .v20_grader import ROOT, EVIDENCE
from .v23_replay import frozen, archived


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    protocol, locked_sha = frozen()
    export_file=EVIDENCE/"v23_session_export_index.json"
    index=json.loads(export_file.read_bytes())
    if index["protocol_sha256"] != locked_sha or index["session_count"]!=8:
        raise ValueError("session export provenance mismatch")
    states={}
    for record in index["sessions"]:
        sid=record["session_id"]
        if sid in states:
            raise ValueError("duplicate session")
        for f in record["files"]:
            path=ROOT/f["path"]
            if not path.is_file() or _sha(path)!=f["sha256"] or path.stat().st_size!=f["bytes"]:
                raise ValueError("portable source/patch file modified")
        state_file=next((f for f in record["files"] if f["path"].endswith("/state.json")),None)
        if not state_file:
            raise ValueError("missing session source")
        state=json.loads((ROOT/state_file["path"]).read_bytes())
        if state["id"]!=sid or state["status"]!="finished":
            raise ValueError("incomplete session")
        states[sid]=state
    outcomes=[]
    totals={"ordinary":{"public":0,"git":0,"seconds":0.0},
            "shared":{"public":0,"git":0,"seconds":0.0}}
    for task in protocol["upstream_real_git_tasks"]:
        task_id=task["id"]
        archival_task,pair,archived_states=archived(task_id)
        file=EVIDENCE/("v23_reuse_"+task_id.replace("-","_")+".json")
        trial=json.loads(file.read_bytes())
        if trial["protocol_sha256"]!=locked_sha or trial["status"]!="completed" or trial["new_model_inference"]:
            raise ValueError("invalid task result")
        result={"task_id":task_id,"raw_path":file.relative_to(ROOT).as_posix(),
                "raw_sha256":_sha(file),"modes":{}}
        for mode in ("ordinary","shared"):
            run=trial["conditions"][mode]
            counts={"public":0,"git":0,"cache":0}
            for arm in ("depth","adaptive"):
                sid=run["outcomes"][arm]["session_id"]
                if sid not in states:
                    raise ValueError("missing portable source state")
                state=states[sid]
                if state["task_id"]!=task_id or state["policy"]!=arm:
                    raise ValueError("wrong task/policy")
                if len(state["attempts"]) != len(archived_states[arm]["attempts"]):
                    raise ValueError("candidate history length changed")
                for i,a in enumerate(state["attempts"]):
                    origin=archived_states[arm]["attempts"][i]
                    if (a["source_sha256"]!=origin["source_sha256"] or
                        a["patch_sha256"]!=origin["patch_sha256"] or
                        a["prompt_sha256"]!=origin["prompt_sha256"] or
                        a["public"]["passed"]!=origin["public"]["passed"] or
                        a["public"]["status"]!=origin["public"]["status"]):
                        raise ValueError("source code/public test differs from frozen real model trace")
                    if hashlib.sha256(a["source"].encode()).hexdigest()!=a["source_sha256"]:
                        raise ValueError("candidate bytes changed")
                    patch=EVIDENCE/"v23_sessions"/sid/(a["id"]+".diff")
                    if not patch.is_file() or hashlib.sha256(patch.read_bytes()).hexdigest()!=a["patch_sha256"]:
                        raise ValueError("candidate patch provenance failed")
                    executed=int(a.get("public_evaluator_invocations",1))
                    applied=int(a.get("git_apply_invocations",1))
                    reused=bool(a.get("reused_public_from_session_id"))
                    if (executed,applied)==(0,0) and not reused:
                        raise ValueError("missing proof of public evidence reuse")
                    if executed+int(reused)!=1 or applied+int(reused)!=1:
                        raise ValueError("model instance neither verified nor executed")
                    if reused:
                        donor=a["reused_public_from_session_id"]
                        if donor not in states:
                            raise ValueError("unverified shared donor")
                        candidates=states[donor]["attempts"]
                        donor_attempt=next((r for r in candidates if r["id"]==a["reused_public_from_attempt_id"]),None)
                        if donor_attempt is None or donor_attempt["patch_sha256"]!=a["patch_sha256"]:
                            raise ValueError("invalid source donor")
                        if donor_attempt.get("reused_public_from_session_id"):
                            raise ValueError("reuse chain not allowed")
                    counts["public"]+=executed
                    counts["git"]+=applied
                    counts["cache"]+=int(reused)
                hidden=state["hidden"]
                r=run["outcomes"][arm]
                if hidden!=r["final_hidden"] or r["full_success"]!=archival_task["reference_hidden_result"][arm]:
                    raise ValueError("independent hidden test correctness changed")
            if counts["public"]!=run["actual_public_evaluator_calls"] or counts["git"]!=run["actual_git_apply_calls"] or counts["cache"]!=run["reused_receipts"]:
                raise ValueError("unjustified efficiency counters")
            result["modes"][mode]={
                "public_docker_runs":counts["public"],
                "git_apply_runs":counts["git"],
                "cache_reuse_hits":counts["cache"],
                "wall_seconds":run["wall_seconds"],
                "full_hidden_outcomes":{a:run["outcomes"][a]["full_success"]
                                        for a in ("depth","adaptive")},
            }
            totals[mode]["public"]+=counts["public"]
            totals[mode]["git"]+=counts["git"]
            totals[mode]["seconds"]+=run["wall_seconds"]
        for arm in ("depth","adaptive"):
            if result["modes"]["ordinary"]["full_hidden_outcomes"][arm] != result["modes"]["shared"]["full_hidden_outcomes"][arm]:
                raise ValueError("optimization changed heldout success")
        outcomes.append(result)
    ordinary,optimized=totals["ordinary"],totals["shared"]
    if optimized["public"]>=ordinary["public"] or optimized["git"]>=ordinary["git"]:
        raise ValueError("optimization did not actually reduce real work")
    return {
        "schema":"nykra-v23-real-repository-public-evaluation-deduplication-v1",
        "frozen_protocol_sha256":locked_sha,
        "protocol_source":"all original actual model patches sourced unchanged from v22",
        "actual_new_codex_or_external_model_calls":0,
        "tasks_replayed":len(outcomes),"condition_orders":[x["condition_order"] for x in protocol["upstream_real_git_tasks"]],
        "ordinary_public_docker_calls":ordinary["public"],
        "nykra_shared_public_docker_calls":optimized["public"],
        "public_docker_calls_avoided":ordinary["public"]-optimized["public"],
        "public_docker_call_reduction_pct":round(100*(ordinary["public"]-optimized["public"])/ordinary["public"],1),
        "ordinary_git_apply_calls":ordinary["git"],
        "nykra_shared_git_apply_calls":optimized["git"],
        "actual_git_apply_calls_avoided":ordinary["git"]-optimized["git"],
        "ordinary_total_wall_seconds":round(ordinary["seconds"],4),
        "nykra_shared_total_wall_seconds":round(optimized["seconds"],4),
        "observed_total_wall_seconds_saved":round(ordinary["seconds"]-optimized["seconds"],4),
        "observed_wall_reduction_pct":round(100*(ordinary["seconds"]-optimized["seconds"])/ordinary["seconds"],1),
        "identical_public_results":True,
        "independent_final_hidden_outcomes_preserved":True,
        "portable_session_count":len(states),
        "portable_export_sha256":_sha(export_file),
        "general_model_correctness_uplift_proven":False,
        "new_model_token_savings_observed":False,
        "original_historical_model_token_cost_not_included":True,
        "scope":"Only duplicate exact code/parent/prompt/evaluator work across 2 policy branches; no guaranteed speedup on independent unrelated requests.",
        "limitations":"Two previously used defects, one replay each; real Docker runs and wall clock but order/warmup confounding, no statistical distribution; no new model calls, model outputs are frozen from previous source. Git/Docker work saved when duplicate contexts occur, not new ability to repair.",
        "tasks":outcomes,
    }


def save():
    path=EVIDENCE/"v23_reuse_summary.json"
    if path.exists():
        raise ValueError("will not overwrite measured evidence")
    report=audit()
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return path
