"""v0.19: controlled policy fork from a shared, independently evaluated prefix.

One prefix is generated and graded ONCE per task. Both arms inherit exact same
candidate text, public results, tokens and ancestry. After three genuine failed
public tests, actual shared select_next must disagree at decision #4:
depth revises latest parent, adaptive starts an independent root.

This exploratory study reuses previously evaluated BugsInPy issues, not fresh
held-out instances. Model sampling after the fork remains stochastic; equal
decision budgets are not hard equal token/latency ceilings.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .exploration_policy import select_next
from .real_issue_v18 import ROOT, grade, manifest as v18_manifest, source_bytes
from .repository_repair_trial import extract_function, invoke_codex

PROTOCOL = ROOT / "docs/evidence/v19_protocol.json"
EVIDENCE = ROOT / "docs/evidence"


def freeze_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol() -> tuple[dict, str]:
    raw = PROTOCOL.read_bytes()
    p = json.loads(raw)
    current, v18_sha = v18_manifest()
    if p["id"] != "nykra-controlled-prefix-fork-v1":
        raise ValueError("unknown fork protocol")
    if p["model"] != current["model"]:
        raise ValueError("model differs from v0.18")
    if p["source_v18_protocol_sha256"] != v18_sha:
        raise ValueError("underlying independent hidden verifier changed")
    if [t["id"] for t in current["tasks"]] != p["task_ids"]:
        raise ValueError("task population changed")
    if p["shared_prefix_attempts"] != 3 or p["continuations_per_arm"] != 2:
        raise ValueError("unexpected attempt allocation")
    if p["total_policy_budget"] < 5:
        raise ValueError("no room to force fork")
    for task in current["tasks"]:
        name = ("v18_pysnooper_3.json" if task["project"] == "PySnooper"
                else f"v18_youtube_dl_{task['bug_id']}.json")
        prior = EVIDENCE / name
        if freeze_sha(prior) != p["v18_reproduction_evidence_sha256"][task["id"]]:
            raise ValueError("prior independent eligibility evidence changed")
        d = json.loads(prior.read_bytes())
        if d["protocol_sha256"] != v18_sha or not d["prevalidation"]["eligible"]:
            raise ValueError("unverified issue")
    return p, hashlib.sha256(raw).hexdigest()


def _task(task_id: str) -> dict:
    d, _ = v18_manifest()
    for task in d["tasks"]:
        if task["id"] == task_id:
            return task
    raise ValueError("unregistered task")


def _source(task: dict) -> str:
    return extract_function(source_bytes(
        task, task["buggy_commit"], task["source_file"]).decode("utf-8"),
        task["function"])


def _context(task: dict, source: str) -> str:
    return (
        "Repair a historical Python software defect. Return only a JSON "
        'object {"source":"one complete top-level Python function definition"}. '
        "Preserve the existing function name, signature and module imports. "
        "No tools or internet lookup; respond with source only. "
        "Only the specified function is replaced.\n"
        "PROJECT: " + task["project"] +
        "\nISSUE: " + task["issue"] +
        "\nFUNCTION: " + task["function"] +
        "\nBUGGY FUNCTION:\n" + source)


def _checkpoint(path: Path, result: dict) -> None:
    stage = path.with_suffix(".partial")
    stage.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    os.replace(stage, path)


def _steps(attempts: list[dict]) -> list[dict]:
    return [{"id": x["id"], "position": i, "parent_id": x["parent_attempt_id"],
             "score": float(x["public"].get("passed") is True)}
            for i, x in enumerate(attempts)]


def _call(task: dict, *, id_: str, action: dict, prompt: str,
          timeout: int, proposer=None) -> dict:
    model = (proposer(prompt, timeout) if proposer else
             invoke_codex(prompt, timeout=timeout))
    candidate = model.get("source")
    if model.get("status") == "ok" and isinstance(candidate, str):
        public = grade(task, mode="public", candidate=candidate)
    else:
        public = {"status": "model_unavailable", "passed": False}
    return {
        "id": id_, "kind": action["kind"],
        "parent_attempt_id": action["parent_attempt_id"],
        "source": candidate,
        "source_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                         if isinstance(candidate, str) else None,
        "model_status": model.get("status"),
        "model_seconds": model.get("seconds"),
        "tokens_reported": model.get("tokens"),
        "public": public,
    }


def _usage(attempts: list[dict]) -> dict:
    seconds = sum(float(a["model_seconds"] or 0) for a in attempts)
    valid_tokens = [a["tokens_reported"] for a in attempts
                    if type(a["tokens_reported"]) is int and a["tokens_reported"] >= 0]
    return {"model_seconds": round(seconds, 3),
            "reported_tokens": sum(valid_tokens),
            "tokens_complete": len(valid_tokens) == len(attempts)}


def _remaining(attempts: list[dict], p: dict) -> tuple[bool, str]:
    usage = _usage(attempts)
    if not usage["tokens_complete"]:
        return False, "missing_model_token_counter"
    if usage["reported_tokens"] >= p["soft_tokens_for_continuation_arm"]:
        return False, "soft_token_budget_reached"
    if usage["model_seconds"] >= p["model_seconds_for_continuation_arm"]:
        return False, "model_time_budget_reached"
    return True, "ok"


def _prefix_prompt(task: dict, broken: str, history: list[dict],
                   action: dict) -> str:
    base = _context(task, broken)
    if not history:
        return base + "\nProduce a first independent candidate."
    parent = next(x for x in history if x["id"] == action["parent_attempt_id"])
    return (base + "\nPREVIOUS CANDIDATE:\n" + str(parent["source"] or "(invalid)") +
            "\nPUBLIC FEEDBACK: " + json.dumps({
                "status": parent["public"]["status"],
                "passed": parent["public"]["passed"]}) +
            "\nRevise that evaluated candidate.")


def _fork_prompt(task: dict, broken: str, common: list[dict],
                 arm_history: list[dict], action: dict) -> str:
    # Exactly the same task description and shared public status summary for
    # both policies. Action-specific parent source differs by design.
    common_statuses = [{"attempt": a["id"], "status": a["public"]["status"],
                        "passed": a["public"]["passed"]} for a in common]
    prefix = (_context(task, broken) +
              "\nTHREE SHARED ATTEMPTS WERE EVALUATED ONCE FOR BOTH ARMS. "
              "Their public outcomes:\n" + json.dumps(common_statuses))
    if action["kind"] == "new_root":
        return (prefix +
                "\nEXPLORATION ACTION: Start an independent new root from "
                "the original issue. Do not edit any previous candidate. "
                "Derive a fresh complete function.")
    if action["kind"] != "revise":
        raise ValueError("unknown branch action")
    parent = next(x for x in arm_history if x["id"] == action["parent_attempt_id"])
    return (prefix + "\nEXPLORATION ACTION: Revise the selected evaluated parent.\n"
            "SELECTED PARENT SOURCE:\n" + str(parent["source"] or "(invalid)") +
            "\nSELECTED PARENT PUBLIC FEEDBACK:\n" + json.dumps(
                {"status": parent["public"]["status"],
                 "passed": parent["public"]["passed"]}) +
            "\nReturn one corrected complete function.")


def make_shared_prefix(task: dict, broken: str, p: dict, *, proposer=None,
                       checkpoint=None) -> tuple[list[dict], str]:
    history: list[dict] = []
    for index in range(p["shared_prefix_attempts"]):
        action = select_next(policy="depth", steps=_steps(history),
                             budget=p["total_policy_budget"])
        if action is None:
            return history, "public_solved"
        timeout = p["max_seconds_per_model_call"]
        attempt = _call(task, id_=f"attempt-{index+1}", action=action,
                        prompt=_prefix_prompt(task, broken, history, action),
                        timeout=timeout, proposer=proposer)
        history.append(attempt)
        if checkpoint:
            checkpoint(history)
        if attempt["public"].get("passed") is True:
            return history, "public_solved"
        if attempt["public"].get("status") != "test_failed":
            return history, "prefix_infrastructure_or_invalid"
    return history, "failed_prefix_ready"


def fork_actions(prefix: list[dict], p: dict) -> dict:
    if len(prefix) != 3 or any(x["public"]["status"] != "test_failed"
                               for x in prefix):
        raise ValueError("fork requires three exactly shared public failures")
    steps = _steps(prefix)
    baseline = select_next(policy="depth", steps=steps,
                           budget=p["total_policy_budget"])
    guided = select_next(policy="adaptive", steps=steps,
                         budget=p["total_policy_budget"])
    if (baseline != {"kind": "revise", "parent_attempt_id": prefix[-1]["id"]} or
            guided != {"kind": "new_root", "parent_attempt_id": None}):
        raise RuntimeError("no actual exploration-policy divergence")
    return {"baseline": baseline, "nykra": guided}


def continue_arm(task: dict, broken: str, prefix: list[dict],
                 p: dict, arm: str, *, proposer=None, checkpoint=None) -> dict:
    if arm not in ("baseline", "nykra"):
        raise ValueError("bad arm")
    own: list[dict] = []
    shared = list(prefix)
    stop_reason = "attempt_limit"
    for i in range(p["continuations_per_arm"]):
        allowed, reason = _remaining(own, p)
        if not allowed:
            stop_reason = reason
            break
        history = shared + own
        action = select_next(policy="depth" if arm == "baseline" else "adaptive",
                             steps=_steps(history), budget=p["total_policy_budget"])
        if action is None:
            stop_reason = "public_solved"
            break
        usage = _usage(own)
        seconds_left = p["model_seconds_for_continuation_arm"] - usage["model_seconds"]
        timeout = min(p["max_seconds_per_model_call"], max(1, int(seconds_left)))
        prompt = _fork_prompt(task, broken, prefix, history, action)
        attempt = _call(task, id_=f"attempt-{len(history)+1}", action=action,
                        prompt=prompt, timeout=timeout, proposer=proposer)
        own.append(attempt)
        if checkpoint:
            checkpoint(own)
        if attempt["public"].get("passed") is True:
            stop_reason = "public_solved"
            break
    chosen = next((a for a in own if a["public"].get("passed") is True), None)
    # Grading happens once after final selection. Neither model prompt nor the
    # policy receives hidden results, and shared prefix has no hidden evaluation.
    hidden = grade(task, mode="hidden", candidate=chosen["source"]) if chosen else {
        "status": "no_public_solution", "passed": False}
    return {"arm": arm, "common_prefix_sha256": hashlib.sha256(
                json.dumps(prefix, sort_keys=True).encode()).hexdigest(),
            "continuation": own,
            "continuation_calls": len(own),
            "first_action": ({"kind": own[0]["kind"],
                              "parent_attempt_id": own[0]["parent_attempt_id"]}
                             if own else None),
            "selected_id": chosen["id"] if chosen else None,
            "public_pass": chosen is not None,
            "hidden_pass": hidden["passed"],
            "full_success": bool(chosen) and bool(hidden["passed"]),
            "final_hidden": hidden,
            "continuation_usage": _usage(own),
            "stop_reason": stop_reason,
            "hard_token_limit_enforced": False}


def run_task(task_id: str, output: Path, *, approve=False, proposer=None) -> dict:
    if approve is not True:
        raise ValueError("explicit execution approval required")
    p, protocol_sha = protocol()
    if task_id not in p["task_ids"]:
        raise ValueError("task not preregistered")
    if output.exists():
        raise ValueError("refusing to overwrite evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    task = _task(task_id)
    report = {"task_id": task_id, "protocol_sha256": protocol_sha,
              "model": p["model"], "status": "shared_prefix",
              "shared_prefix": [], "shared_prefix_reason": None,
              "fork_actions": None, "arms": []}
    _checkpoint(output, report)
    broken = _source(task)
    def prefix_checkpoint(history):
        report["shared_prefix"] = history
        _checkpoint(output, report)
    common, reason = make_shared_prefix(task, broken, p, proposer=proposer,
                                        checkpoint=prefix_checkpoint)
    report["shared_prefix_reason"] = reason
    report["shared_prefix"] = common
    if reason != "failed_prefix_ready":
        report["status"] = "not_forkable"
        _checkpoint(output, report)
        return report
    actions = fork_actions(common, p)
    report["fork_actions"] = actions
    report["status"] = "forking"
    _checkpoint(output, report)
    for arm in p["arm_order"][task_id]:
        pending = []
        def arm_checkpoint(items):
            pending[:] = items
            report["pending_arm"] = {"arm": arm, "attempts": pending}
            _checkpoint(output, report)
        result = continue_arm(task, broken, common, p, arm, proposer=proposer,
                              checkpoint=arm_checkpoint)
        report["arms"].append(result)
        report.pop("pending_arm", None)
        _checkpoint(output, report)
    report["status"] = "completed"
    _checkpoint(output, report)
    return report
