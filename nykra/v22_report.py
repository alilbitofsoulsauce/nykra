"""Machine verification of v0.22 real Git patch workflow evidence and provenance."""
import hashlib
import json
from pathlib import Path

from .agent_workflow import SESSIONS  # live-source consistency checked when available
from .v20_grader import ROOT, EVIDENCE
from .v22_paired import frozen

FILES = {
    "youtube-dl-27": "v22_workflow_pair_youtube_dl_27.json",
    "youtube-dl-43": "v22_workflow_pair_youtube_dl_43.json",
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def aggregate():
    proto, proto_sha = frozen()
    items = []
    totals = {"depth": 0, "adaptive": 0}
    unique_model_calls = 0
    total_git_patches = 0
    actual_forks = 0
    for task_id in proto["tasks"]:
        path = EVIDENCE / FILES[task_id]
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw["protocol_sha256"] != proto_sha or raw["task_id"] != task_id:
            raise ValueError("pair task/protocol mismatched")
        if not raw["preexisting_historical_benchmark"] or raw["causal_or_general_uplift_proven"]:
            raise ValueError("invalid effectiveness qualification")
        if len(raw["generated"]) != raw["total_model_completions"]:
            raise ValueError("model completion count mismatched")
        if sum(x["mode"] == "shared" for x in raw["generated"]) != raw["shared_model_completion_count"]:
            raise ValueError("shared prefix count inaccurate")
        pairs = {}
        for arm in ("depth", "adaptive"):
            r = raw["results"][arm]
            if r["status"] != "finished":
                raise ValueError("uncompleted workflow")
            if r["tested_git_patches"] != r["attempt_count"]:
                raise ValueError("model source was not materialized as Git patch")
            sid = r["session_id"]
            if len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid):
                raise ValueError("invalid session")
            folder = EVIDENCE / "v22_sessions" / sid
            if not (folder / "state.json").is_file():
                raise ValueError("portable session evidence is missing")
            state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
            live = SESSIONS / sid / "state.json"
            if live.exists() and sha(live) != sha(folder / "state.json"):
                raise ValueError("portable session evidence differs from live source")
            if state["evaluator_sha256"] != proto["v21_evaluator_sha256"]:
                raise ValueError("underlying pinned tests changed")
            if state["id"] != sid or state["status"] != "finished":
                raise ValueError("tampered session")
            if state["policy"] != arm or state["task_id"] != task_id:
                raise ValueError("session policy or task mismatch")
            if r["selected_attempt_id"] != state["selected_attempt_id"] or r["final_hidden"] != state["hidden"]:
                raise ValueError("pair state hidden mismatch")
            for attempt in state["attempts"]:
                patch = folder / (attempt["id"] + ".diff")
                if not patch.is_file() or patch.is_symlink() or sha(patch) != attempt["patch_sha256"]:
                    raise ValueError("missing or altered actual source patch")
                if hashlib.sha256(attempt["source"].encode()).hexdigest() != attempt["source_sha256"]:
                    raise ValueError("source hash mismatch")
                if not attempt["actual_git_apply_verified"]:
                    raise ValueError("patch not Git-verified")
            total_git_patches += r["tested_git_patches"]
            totals[arm] += int(r["full_success"])
            pairs[arm] = {
                "success": r["full_success"],
                "attempts": r["attempt_count"],
                "git_patches": r["tested_git_patches"],
                "reported_tokens_including_shared_prefix": r["model_tokens_reported"],
                "reported_model_seconds_including_shared_prefix": r["model_seconds_reported"],
                "missing_token_counters": r["missing_token_counters"],
                "final_hidden_status": r["final_hidden"]["status"] if r["final_hidden"] else None,
                "session_id": sid,
            }
        shared = raw["shared_model_completion_count"]
        for i in range(shared):
            if (raw["results"]["depth"]["ancestry"][i]["patch_sha256"] !=
                    raw["results"]["adaptive"]["ancestry"][i]["patch_sha256"]):
                raise ValueError("purported shared model prefix is not identical")
        if raw["policy_divergence"] is not None:
            actual_forks += 1
            if raw["policy_divergence"]["depth_action"] == raw["policy_divergence"]["adaptive_action"]:
                raise ValueError("fake policy fork")
        unique_model_calls += raw["total_model_completions"]
        items.append({
            "task_id": task_id, "raw_path": path.relative_to(ROOT).as_posix(),
            "raw_sha256": sha(path),
            "shared_model_completions": shared,
            "total_distinct_model_completions": raw["total_model_completions"],
            "genuine_policy_fork": raw["policy_divergence"] is not None,
            "arms": pairs,
        })
    index_path = EVIDENCE / "v22_session_export_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index["v22_protocol_sha256"] != proto_sha or index["session_count"] != 5:
        raise ValueError("portable session registry changed")
    for case in index["files"]:
        for file in case["files"]:
            verified = ROOT / file["path"]
            if not verified.is_file() or sha(verified) != file["sha256"]:
                raise ValueError("portable patch registry checksum mismatch")
    cli=EVIDENCE/"v22_cli_reference_smoke.json"
    standalone=json.loads(cli.read_text(encoding="utf-8"))
    if (not standalone["complete"] or standalone["candidate_origin"] !=
            "UPSTREAM_REFERENCE_CONTROL_NOT_MODEL_GENERATED"):
        raise ValueError("CLI smoke incorrectly attributed to model")
    if standalone["protocol_sha256"] != proto["v21_evaluator_sha256"]:
        raise ValueError("CLI pinned test changed")
    return {
        "schema":"nykra-v22-real-repository-agent-workflow-integration-summary-v1",
        "protocol_sha256":proto_sha,
        "registered_reused_upstream_issues":len(items),
        "tested_workflow_driver":"Rel.AI host + authenticated Codex read-only inference",
        "verified_portable_relai_cli_transport":True,
        "cli_reference_control_excluded_from_model_results":True,
        "actual_distinct_codex_model_calls":unique_model_calls,
        "git_applied_source_patches_in_paired_model_trials":total_git_patches,
        "policy_divergence_task_count":actual_forks,
        "hidden_verified_successes":totals,
        "general_effectiveness_improvement_proven":False,
        "unattended_relai_inference_available":False,
        "native_multi_agent_adapters_verified":False,
        "official_swebench":False,
        "reused_benchmark_tasks_not_independent_research_sample":True,
        "cli_smoke_path":cli.relative_to(ROOT).as_posix(),
        "cli_smoke_sha256":sha(cli),
        "tasks":items,
        "limit":("This tests a portable host-supervised real Git single-function repair "
                 "workflow, NOT arbitrary multi-file autonomous coding. Both tasks "
                 "were reused from v0.21; the only actual policy fork failed in both arms. "
                 "Rel.AI does not independently supply model completions."),
    }

def save():
    path=EVIDENCE/"v22_workflow_summary.json"
    if path.exists():
        raise ValueError("will not overwrite evidence")
    report=aggregate()
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return path
