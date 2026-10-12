"""Counterfactual replay of historical live model outputs with import-only adapter.

Chronological fixed v32 free provider outputs; original strict parser verdicts
stay untouched. Applies a simple deterministic, pre-declared import-preamble
normalizer and REAL pinned Docker public grading. Hidden only on public pass.
No new model inference. This compares parser handling on the SAME model bytes,
not adaptive policies or unseen issues.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from nykra.model_source_normalizer import normalize_function_imports
from nykra.v20_grader import function_at
from nykra.v21_grader import grade, manifest

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"docs/evidence/v32_solved/youtube-dl-43_baseline_depth.json"
RESULT=ROOT/"docs/evidence/v32_solved/youtube-dl-43_chronological_import_replay.json"


def run(approve=False):
    if approve is not True:
        raise ValueError("explicit real Docker replay approval required")
    if RESULT.exists() or RESULT.is_symlink():
        raise ValueError("will not overwrite prior evidence")
    doc,_=manifest()
    task=next(t for t in doc["tasks"] if t["id"]=="youtube-dl-43")
    original=function_at(task,task["buggy_commit"])
    history=json.loads(HISTORY.read_text(encoding="utf-8"))
    assert history["status"]=="provider_excluded"
    assert history["provider_error"].startswith("model provider HTTP 429")
    assert len(history["attempts"])>=4
    public_cache={}
    outcomes=[]
    for a in history["attempts"]:
        if a["original_v31"]:
            continue
        normalized=normalize_function_imports(a["source"],name=task["function"],
                                              original=original)
        candidate=normalized["source"]
        sha=hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        cached=public_cache.get(sha)
        if normalized["status"]=="unrecognized_source":
            public={"status":"model_invalid_contract","passed":False}
            docker_called=False
            original_evaluation=None
        elif cached is not None:
            public=cached["public"]
            docker_called=False
            original_evaluation=cached["attempt"]
        else:
            public=grade(task,mode="public",candidate=candidate)
            docker_called=True
            original_evaluation=None
            if public["status"] in ("test_failed","ok"):
                public_cache[sha]={"attempt":a["id"],"public":public}
        verdict={"attempt_id":a["id"],
                 "model_response_id":a["provider_response_id"],
                 "raw_sha256":a["source_sha256"],
                 "source_normalization":normalized["status"],
                 "imports_moved":normalized["import_statements_moved"],
                 "normalized_sha256":sha,
                 "public":public,"public_docker_called":docker_called,
                 "public_reused_from":original_evaluation}
        outcomes.append(verdict)
        print(json.dumps({"attempt":a["id"],"normalized":normalized["status"],
                          "public":public["status"],"docker":docker_called,
                          "reused_from":original_evaluation}),flush=True)
        if public["status"]=="ok":
            hidden=grade(task,mode="hidden",candidate=candidate)
            verdict["hidden"]=hidden
            print(json.dumps({"hidden_at":a["id"],"status":hidden["status"]}),flush=True)
            if hidden["status"]=="ok":
                break
            if hidden["status"]!="test_failed":
                raise RuntimeError("hidden infrastructure failure, cannot score success")
        if public["status"].startswith("evaluator_"):
            raise RuntimeError("public grader infrastructure failure, cannot continue")
    result={"schema":"nykra-v32-chronological-same-live-source-normalizer-replay-v1",
            "task":"youtube-dl-43","model_source":"real separate frozen 2026-10-12 free model outputs",
            "history_sha256":hashlib.sha256(HISTORY.read_bytes()).hexdigest(),
            "original_historical_provider_exhaustion":"HTTP 429",
            "new_provider_calls":0,
            "no_new_model_source_authored":True,
            "normalization":"AST-based moving allowlisted top-level stdlib imports inside sole original function; original body AST unchanged",
            "model_attempts_seen_before_429":len(history["attempts"]),
            "new_model_attempts_pre_429":len(history["attempts"])-3,
            "retrospectively_checked_attempts":len(outcomes),
            "public_docker_evaluations":sum(x["public_docker_called"] for x in outcomes),
            "public_reuses":sum(x["public_reused_from"] is not None for x in outcomes),
            "earliest_hidden_verified_attempt":next((x["attempt_id"] for x in outcomes
                                                     if x.get("hidden",{}).get("status")=="ok"),None),
            "hidden_verified":any(x.get("hidden",{}).get("status")=="ok" for x in outcomes),
            "original_live_run_was_not_terminated_at_earliest_recoverable_solution":True,
            "not_live_randomized_comparison":True,
            "no_general_accuracy_claim":True,
            "raw_outcomes":outcomes}
    RESULT.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"summary":str(RESULT),"outcomes":len(outcomes),
                      "public_docker":result["public_docker_evaluations"],
                      "first_hidden_verified":result["earliest_hidden_verified_attempt"]}),flush=True)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve",action="store_true")
    args=parser.parse_args()
    report=run(args.approve)
    raise SystemExit(0 if report["hidden_verified"] else 3)
