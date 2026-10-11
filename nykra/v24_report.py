"""Independent task- and source-level audit of v0.24 persistent public caching."""
from __future__ import annotations

import hashlib
import json

from .v20_grader import ROOT,EVIDENCE
from .v24_benchmark import frozen,source_for


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    protocol, protocol_sha=frozen()
    exported=json.loads((EVIDENCE/"v24_session_export_index.json").read_bytes())
    if exported["protocol_sha256"]!=protocol_sha or exported["session_count"]!=12:
        raise ValueError("portable session index provenance failed")
    portable={}
    for line in exported["sessions"]:
        sid=line["session_id"]
        if sid in portable:raise ValueError("duplicate exported session")
        for entry in line["files"]:
            item=ROOT/entry["path"]
            if not item.is_file() or _sha(item)!=entry["sha256"] or item.stat().st_size!=entry["bytes"]:
                raise ValueError("exported source/patch changed")
        f=next((x for x in line["files"] if x["path"].endswith("/state.json")),None)
        if f is None:raise ValueError("missing frozen session state")
        portable[sid]=json.loads((ROOT/f["path"]).read_bytes())
    receipts=json.loads((EVIDENCE/"v24_public_receipt_index.json").read_bytes())
    if receipts["protocol_sha256"]!=protocol_sha or receipts["receipt_count"]!=2:
        raise ValueError("portable public receipt index failed")
    receipt_by_task={}
    for item in receipts["receipts"]:
        file=ROOT/item["path"]
        if not file.is_file() or _sha(file)!=item["sha256"] or file.stat().st_size!=item["bytes"]:
            raise ValueError("public cache receipt changed")
        data=json.loads(file.read_bytes())
        checksum=data.pop("receipt_sha256")
        from .public_cache_v24 import _encode
        if _sha_value(_encode(data))!=checksum:
            raise ValueError("public cache checksum failed")
        if data.get("schema")!="nykra-public-receipt-v24" or "hidden" in data:
            raise ValueError("untrusted cached public receipt")
        if data["inputs"]["task_id"]!=item["task_id"]:
            raise ValueError("wrong cache task")
        receipt_by_task[item["task_id"]]=data
    totals={m:{"docker":0,"git":0,"elapsed":0.0,"hits":0,"hidden_pass":0}
            for m in ("cold","cached")}
    rows=[]
    for task in protocol["cases"]:
        task_id=task["id"]
        source=source_for(task)
        archive_source_sha=_sha_value(source.encode())
        path=EVIDENCE/("v24_cache_"+task_id.replace("-","_")+".json")
        record=json.loads(path.read_bytes())
        if record["status"]!="completed" or record["protocol_sha256"]!=protocol_sha or record["model_source_sha256"]!=archive_source_sha:
            raise ValueError("task result not complete or source mismatch")
        comparisons={}
        for mode in ("cold","cached"):
            result=record["conditions"][mode]
            if len(result["sessions"])!=3 or result["new_model_inference_calls"]!=0:
                raise ValueError("session count or model inference discrepancy")
            counters={"docker":0,"git":0,"hits":0,"hidden_pass":0}
            for index,line in enumerate(result["sessions"]):
                state=portable.get(line["session_id"])
                if state is None or state["status"]!="finished" or len(state["attempts"])!=1:
                    raise ValueError("missing finished real session")
                if state["task_id"]!=task_id or state["evaluator_sha256"]!=protocol["evaluator_sha256"]:
                    raise ValueError("task/evaluator changed")
                expected=task["independent_sessions"][index]
                if state["policy"]!=expected["policy"] or state["enriched_feedback"]!=expected["enriched_feedback"]:
                    raise ValueError("independent session configuration altered")
                attempt=state["attempts"][0]
                if attempt["source_sha256"]!=archive_source_sha or _sha_value(attempt["source"].encode())!=archive_source_sha:
                    raise ValueError("model-generated source changed")
                patch_file=EVIDENCE/"v24_sessions"/state["id"]/"attempt-1.diff"
                if _sha(patch_file)!=attempt["patch_sha256"] or not attempt["actual_git_apply_verified"]:
                    raise ValueError("actual/verified patch evidence changed")
                cache_hit=bool(attempt.get("public_cache_hit"))
                if cache_hit:
                    cache_receipt=receipt_by_task[task_id]
                    if (attempt["public_cache_key"]!=cache_receipt["cache_key"]
                            or attempt["patch_sha256"]!=_sha_value(cache_receipt["patch"].encode())
                            or attempt["public"]!=cache_receipt["public"]):
                        raise ValueError("cached verdict not matching verified local public receipt")
                if cache_hit and mode=="cold":
                    raise ValueError("uncached baseline hit cache")
                if int(attempt["public_evaluator_invocations"])+int(cache_hit)!=1 or int(attempt["git_apply_invocations"])+int(cache_hit)!=1:
                    raise ValueError("cached session has duplicate or missing real evaluator")
                if (attempt["public"]["status"]!=line["public_status"] or
                        attempt["public"]["passed"]!=line["public_passed"] or
                        attempt["patch_sha256"]!=line["patch_sha256"] or
                        attempt["public_cache_hit"]!=line["public_cache_hit"] or
                        state["hidden"]["status"]!=line["hidden_status"]):
                    raise ValueError("independent public or hidden results differed")
                success=(attempt["public"]["passed"] and state["hidden"]["passed"] is True)
                if bool(success)!=line["full_success"] or bool(success)!=task["historical_public_pass"]:
                    raise ValueError("independent hidden correctness was changed")
                counters["docker"]+=attempt["public_evaluator_invocations"]
                counters["git"]+=attempt["git_apply_invocations"]
                counters["hits"]+=int(cache_hit)
                counters["hidden_pass"]+=int(bool(success))
            if (counters["docker"]!=result["public_docker_calls"] or
                    counters["git"]!=result["git_apply_calls"] or
                    counters["hits"]!=result["cache_hits"] or
                    counters["hidden_pass"]!=result["hidden_verified_passes"]):
                raise ValueError("recorded work counts unsupported")
            comparisons[mode]={"public_docker_calls":counters["docker"],
                               "git_apply_calls":counters["git"],
                               "cache_hits":counters["hits"],
                               "hidden_passes":counters["hidden_pass"],
                               "wall_seconds":result["wall_seconds"]}
            totals[mode]["docker"]+=counters["docker"]
            totals[mode]["git"]+=counters["git"]
            totals[mode]["hits"]+=counters["hits"]
            totals[mode]["hidden_pass"]+=counters["hidden_pass"]
            totals[mode]["elapsed"]+=result["wall_seconds"]
        if (comparisons["cold"]["hidden_passes"] != comparisons["cached"]["hidden_passes"]
                or comparisons["cold"]["public_docker_calls"]!=3
                or comparisons["cached"]["public_docker_calls"]!=1):
            raise ValueError("wrong experiment or changed correctness")
        rows.append({"task_id":task_id,"raw_path":path.relative_to(ROOT).as_posix(),
                     "raw_sha256":_sha(path),"conditions":comparisons})
    a,b=totals["cold"],totals["cached"]
    return {"schema":"nykra-v24-independent-session-exact-public-receipts-summary-v1",
            "protocol_sha256":protocol_sha,
            "registered_historical_issues":len(rows),
            "independent_sessions_per_condition_per_issue":3,
            "total_independent_session_runs":12,
            "total_new_external_model_proposals":0,
            "ordinary_actual_public_docker_calls":a["docker"],
            "nykra_cached_actual_public_docker_calls":b["docker"],
            "real_public_tests_avoided":a["docker"]-b["docker"],
            "public_docker_reduction_pct":round(100*(a["docker"]-b["docker"])/a["docker"],1),
            "ordinary_actual_git_apply_calls":a["git"],
            "nykra_cached_actual_git_apply_calls":b["git"],
            "actual_git_apply_calls_avoided":a["git"]-b["git"],
            "nykra_cache_hits":b["hits"],
            "ordinary_elapsed_seconds":round(a["elapsed"],4),
            "nykra_cache_elapsed_seconds":round(b["elapsed"],4),
            "observed_seconds_saved":round(a["elapsed"]-b["elapsed"],4),
            "observed_wall_reduction_pct":round(100*(a["elapsed"]-b["elapsed"])/a["elapsed"],1),
            "independent_hidden_successes_ordinary":a["hidden_pass"],
            "independent_hidden_successes_cached":b["hidden_pass"],
            "historical_patch_outcomes_preserved":True,
            "general_agent_correctness_advantage_proven":False,
            "model_token_savings_measured":False,
            "cache_security":"trusted local cache with input-hash integrity checks; not tamperproof against a process with full local user filesystem access",
            "scope":"Exact same source/upstream Git/test/evaluator/Docker inputs across independent authorized policy/feedback sessions; no unrelated-task speed guarantee",
            "limitations":"2 previously used upstream issues, three independent sessions per condition each, 1 replay per issue with counterbalanced condition order; observed wall time includes runtime warmup and hidden grading. This measures engineering duplication, not improved coding model intelligence.",
            "portable_sessions_sha256":_sha(EVIDENCE/"v24_session_export_index.json"),
            "portable_public_receipts_sha256":_sha(EVIDENCE/"v24_public_receipt_index.json"),
            "tasks":rows}


def _sha_value(blob):
    return hashlib.sha256(blob).hexdigest()


def save():
    path=EVIDENCE/"v24_summary.json"
    if path.exists():raise ValueError("will not overwrite result")
    output=audit()
    path.write_text(json.dumps(output,indent=2)+"\n")
    return path
