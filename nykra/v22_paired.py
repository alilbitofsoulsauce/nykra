"""v0.22 matched host-driven real Git patch workflow integration smoke.

One shared model proposal is submitted to both depth/adaptive session drivers
while their policy decisions are IDENTICAL. Once decisions differ, each arm
calls the same authorized inference provider independently. All candidates
are actually git-applied in scratch checkouts and public-tested in Docker.
Only after model generation ends is each arm hidden-graded.

These are previously used historical tasks: integration/engineering evidence,
NOT an independent coding-agent success-rate experiment.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agent_workflow import start, next_request, submit, finalize, summary
from .repository_repair_trial import invoke_codex
from .v21_grader import EVIDENCE, manifest

PROTOCOL = EVIDENCE / "v22_workflow_protocol.json"

def frozen():
    raw = PROTOCOL.read_bytes()
    data = json.loads(raw)
    _, src_sha = manifest()
    if data["id"] != "nykra-real-git-workflow-integration-v1":
        raise ValueError("unknown integration protocol")
    if data["v21_evaluator_sha256"] != src_sha:
        raise ValueError("upstream fixed-task evaluator changed")
    if data["budget_per_arm"] != 4 or data["tasks"] != [
            "youtube-dl-27", "youtube-dl-43"]:
        raise ValueError("changed or unreviewed integration smoke population")
    if data["driver"] != "codex-inference":
        raise ValueError("missing authenticated inference driver")
    return data, hashlib.sha256(raw).hexdigest()

def _response(response, request, label):
    if response.get("status") != "ok" or not isinstance(response.get("source"), str):
        raise ValueError("model did not return a valid candidate; do not impute success")
    evaluated = submit(request["session_id"], response["source"], approve=True,
                       tokens=response.get("tokens"), model_seconds=response.get("seconds"),
                       agent_label=label)
    return evaluated["next"]

def run_pair(task_id, *, provider=None, approve=False):
    if approve is not True:
        raise ValueError("explicit model inference and sandbox execution authorization required")
    protocol, sha = frozen()
    if task_id not in protocol["tasks"]:
        raise ValueError("task not frozen")
    proposer = provider if provider is not None else (
        lambda prompt, timeout: invoke_codex(prompt, timeout=timeout))
    streams = {}
    for arm in ("depth", "adaptive"):
        streams[arm] = start(task_id=task_id, policy=arm,
                             budget=protocol["budget_per_arm"],
                             driver="codex-inference",
                             enriched_feedback=True, approve=True)
    generated = []
    divergence = None
    # Strictly serial. A shared proposal is inferred ONCE then submitted in
    # both arms, not separately sampled and called "identical".
    while any(x["agent_required"] for x in streams.values()):
        l, r = streams["depth"], streams["adaptive"]
        can_share = (l["agent_required"] and r["agent_required"] and
                     l["request"] == r["request"] and l["prompt"] == r["prompt"])
        if can_share:
            response = proposer(l["prompt"], protocol["max_seconds_per_call"])
            generated.append({"mode": "shared", "request_kind": l["request"]["kind"],
                              "source_sha256": hashlib.sha256(
                                  str(response.get("source","")).encode()).hexdigest(),
                              "status": response.get("status"),
                              "tokens": response.get("tokens")})
            for arm in ("depth", "adaptive"):
                streams[arm] = _response(response, streams[arm], "codex-shared")
        else:
            if divergence is None and l["agent_required"] and r["agent_required"]:
                divergence = {"depth_action": l["request"],
                              "adaptive_action": r["request"],
                              "after_common_attempts": len([x for x in generated
                                                             if x["mode"] == "shared"])}
            for arm in ("depth", "adaptive"):
                request = streams[arm]
                if not request["agent_required"]:
                    continue
                response = proposer(request["prompt"], protocol["max_seconds_per_call"])
                generated.append({"mode": arm,
                                  "request_kind": request["request"]["kind"],
                                  "source_sha256": hashlib.sha256(
                                      str(response.get("source","")).encode()).hexdigest(),
                                  "status": response.get("status"),
                                  "tokens": response.get("tokens")})
                streams[arm] = _response(response, request, "codex-"+arm)
    # The hidden checks cannot influence any model prompt: all inference is
    # complete before either branch is finalized.
    results = {arm: finalize(streams[arm]["session_id"], approve=True)
               for arm in ("depth","adaptive")}
    return {
        "schema": "nykra-v22-agent-workflow-paired-integration-v1",
        "protocol_sha256": sha,
        "task_id": task_id, "driver": "relai-hosted-codex-inference",
        "shared_model_completion_count": sum(x["mode"]=="shared" for x in generated),
        "total_model_completions": len(generated),
        "generated": generated, "policy_divergence": divergence,
        "results": results,
        "preexisting_historical_benchmark": True,
        "causal_or_general_uplift_proven": False,
        "qualification": ("Actual Git apply to disposable upstream checkout and "
                          "Docker grading; single-function patch protocol, "
                          "not arbitrary autonomous multi-file agent editing.")
    }

def save_pair(task_id, *, provider=None, approve=False):
    proto, _ = frozen()
    filename = "v22_workflow_pair_" + task_id.replace("-", "_") + ".json"
    file = EVIDENCE / filename
    if file.exists():
        raise ValueError("will not overwrite experiment evidence")
    outcome = run_pair(task_id, provider=provider, approve=approve)
    file.write_text(json.dumps(outcome,indent=2)+"\n",encoding="utf-8")
    return outcome
