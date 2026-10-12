"""Pre-registered v0.31 real historical repair efficiency study.

Run one frozen task at a time. Authenticated free-model completions per arm
are INDEPENDENT. No test or model code runs on the host. Graders run cloned
historic Git sources inside existing pinned, offline restricted Docker images.
No untrusted prompt instructions can change evaluator or provider parameters.
Raw model output, tests, and receipts are archived; credentials never are.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from nykra.free_model_client import FreeModelError, generate, generate_cached
from nykra.multifile_workflow import _repeated_public_failure
from nykra.repair_feedback import public_message, validate_replacement
from nykra.v20_grader import function_at
from nykra.v20_grader import grade as grade20
from nykra.v20_grader import manifest as manifest20
from nykra.v21_grader import grade as grade21
from nykra.v21_grader import manifest as manifest21

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/evidence/v31_live_study_protocol.json"
PROTOCOL_SHA = "d50af1b42f21ebf0361a315d37fe822abe992bd5a32d88dac32cc6461f951f24"
ISSUE_GRADERS = {"v20": (manifest20, grade20), "v21": (manifest21, grade21)}
INFRA_STATUSES = ("evaluator_", "base_image_", "build_error",
                  "setup_error", "timeout", "image_inspect_error")
MAX_PUBLIC_DIAGNOSTIC = 900


def sha(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def candidate_from_model(raw):
    """Remove only a whole-response Markdown fence; never guess source spans."""
    trimmed = raw.strip()
    found = re.fullmatch(r"```(?:python|py)?\s*\n(.*?)\n```",
                         trimmed, flags=re.DOTALL | re.IGNORECASE)
    if found:
        trimmed = found.group(1)
    return trimmed.rstrip() + "\n"


def prompt_for(task, original, attempt, prior):
    """Same first prompt per task for both independent arms, public feedback only."""
    text = (
        "Repair a genuine historic Python library bug. Return ONLY ONE complete "
        "top-level Python function definition in plain source code. "
        "NO markdown, JSON, preface or extra functions. Preserve the exact "
        "existing signature (including defaults and **kwargs); module imports "
        "and helper functions already exist. You may use imports inside "
        "the function. Do not invent global helper names.\n"
        f"ISSUE: {task['issue']}\n"
        f"FUNCTION: {task['function']}\n"
        f"ORIGINAL SOURCE:\n{original}\n"
        f"PUBLIC REGRESSION TARGET: {task['public_test']}\n"
    )
    if prior:
        previous = prior[-1]
        text += ("PREVIOUS FAILED SOURCE (do not repeat unchanged):\n"
                 + previous["source"][:8500]
                 + "\n" + public_message(previous["public"], enriched=True)
                 + "\nReturn a corrected function source and address the public failure.")
    else:
        text += "Construct a first corrected implementation from the issue and source."
    return text


def _write_checkpoint(location, document):
    location.parent.mkdir(parents=True, exist_ok=True)
    temp = location.with_suffix(".partial")
    temp.write_text(json.dumps(document, indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8", newline="\n")
    os.replace(temp, location)


def run(*, task_index, cache_root, approve, output_dir):
    if approve is not True:
        raise ValueError("explicit permission for free inference + Docker required")
    if type(task_index) is not int or task_index not in (0, 1, 2):
        raise ValueError("valid frozen task index 0..2 required")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY environment credential required")
    if not isinstance(cache_root, Path):
        raise ValueError("an operator-private cache location is required")
    frozen = PROTOCOL.read_bytes()
    if hashlib.sha256(frozen).hexdigest() != PROTOCOL_SHA:
        raise ValueError("frozen v31 protocol digest changed")
    protocol = json.loads(frozen)
    description = protocol["tasks"][task_index]
    family = description["grader"]
    definition, grader = ISSUE_GRADERS[family]
    source_doc, source_sha = definition()
    if source_sha != description["preregistered_protocol_sha256"]:
        raise ValueError("historical upstream grader changed")
    task = next(x for x in source_doc["tasks"] if x["id"] == description["id"])
    broken = function_at(task, task["buggy_commit"])
    if sha(broken) != description["original_function_sha256"]:
        raise ValueError("historical source changed from frozen protocol")
    outfile = output_dir / (task["id"] + ".json")
    if outfile.exists() or outfile.is_symlink():
        raise ValueError("refusing to overwrite an existing live study result")
    report = {
        "schema": "nykra-v31-task-live-comparison-v1",
        "task_id": task["id"], "grader": family,
        "frozen_protocol_sha256": PROTOCOL_SHA,
        "upstream_buggy_commit": task["buggy_commit"],
        "upstream_fixed_commit": task["fixed_commit"],
        "original_function_sha256": sha(broken),
        "model": protocol["model"], "model_budget_per_arm": 3,
        "grade_public_only_during_iteration": True,
        "status": "running", "arms": [], "hidden_evaluated_after_arms": False,
    }
    _write_checkpoint(outfile, report)
    arms = protocol["arm_execution_order_by_task"][task_index]
    for arm_name in arms:
        optimized = arm_name == "nykra_optimized_depth"
        attempts = []
        provider_calls = 0
        grader_calls = 0
        grader_reuses = 0
        calls_avoided = 0
        reported_tokens = 0
        report_arm = {
            "arm": arm_name, "optimized": optimized,
            "policy": "depth", "status": "in_progress",
            "attempts": attempts,
        }
        report["arms"].append(report_arm)
        _write_checkpoint(outfile, report)
        verified_cache = {}
        for ordinal in range(1, 4):
            if optimized:
                # Use the SAME actual tested-failure guard as multi-workflow.
                state = {"halt_on_repeat_failure": True,
                         "attempts": [{
                             "status": a["public"]["status"],
                             "tests_passed": a["public"]["passed"],
                             "patch_sha256": a["source_sha256"],
                         } for a in attempts]}
                if _repeated_public_failure(state):
                    report_arm["stop_reason"] = "paused_repeated_failed_patch"
                    break
            if any(a["public"].get("passed") for a in attempts):
                report_arm["stop_reason"] = "public_pass"
                break
            query = prompt_for(task, broken, ordinal, attempts)
            started = time.monotonic()
            try:
                if optimized:
                    # Private cache scope is specific to *this* task and arm.
                    completion = generate_cached(
                        query, model=protocol["model"],
                        max_tokens=protocol["model_max_tokens"],
                        timeout=protocol["model_timeout_seconds"],
                        cache_dir=cache_root / task["id"] / arm_name,
                        approve=True,
                    )
                else:
                    completion = generate(
                        query, model=protocol["model"],
                        max_tokens=protocol["model_max_tokens"],
                        timeout=protocol["model_timeout_seconds"],
                        approve=True,
                    )
            except FreeModelError as err:
                report_arm["status"] = "provider_infrastructure_excluded"
                report_arm["provider_error_class"] = str(err)[:120]
                break
            receipt = completion["receipt"]
            if "provider_called_this_request" in receipt:
                provider_calls += int(receipt["provider_called_this_request"])
                calls_avoided += int(receipt["provider_calls_avoided"])
                current = receipt["provider_tokens_this_request"]
                if type(current) is int:
                    reported_tokens += current
            else:
                provider_calls += 1
                current = receipt["tokens"].get("total_tokens")
                if type(current) is int:
                    reported_tokens += current
                elif all(type(receipt["tokens"].get(k)) is int
                         for k in ("prompt_tokens", "completion_tokens")):
                    reported_tokens += (receipt["tokens"]["prompt_tokens"]
                                        + receipt["tokens"]["completion_tokens"])
            raw = completion["text"]
            proposed = candidate_from_model(raw)
            identity = sha(proposed)
            problem = validate_replacement(
                proposed, name=task["function"], original=broken)
            reused_public_from = None
            if problem is not None:
                public = problem
            elif optimized and identity in verified_cache:
                public = verified_cache[identity]["public"].copy()
                reused_public_from = verified_cache[identity]["attempt_number"]
                grader_reuses += 1
            else:
                public = grader(task, mode="public", candidate=proposed)
                grader_calls += 1
                if optimized and public["status"] == "test_failed":
                    verified_cache[identity] = {
                        "attempt_number": ordinal, "public": public.copy()}
            attempt = {
                "attempt_number": ordinal, "source_sha256": identity,
                "model_raw_output_sha256": sha(raw),
                "model_raw_output": raw, "source": proposed,
                "prompt_sha256": sha(query),
                "model_response_id": receipt.get("response_id"),
                "model_provider_reported_tokens": receipt.get("tokens"),
                "model_provider_reported_cost": receipt.get("cost"),
                "model_cache_hit": bool(receipt.get("cache_hit", False)),
                "inference_plus_public_work_seconds": round(time.monotonic() - started, 3),
                "public": public,
                "public_grade_reused": reused_public_from is not None,
                "public_grade_source_attempt": reused_public_from,
            }
            attempts.append(attempt)
            report_arm.update({
                "model_provider_calls": provider_calls,
                "model_calls_avoided": calls_avoided,
                "provider_reported_tokens": reported_tokens,
                "public_grader_calls": grader_calls,
                "public_grader_reuses": grader_reuses,
                "model_attempts": len(attempts),
            })
            _write_checkpoint(outfile, report)
            print(json.dumps({"task": task["id"], "arm": arm_name, "attempt": ordinal,
                              "status": public["status"], "same_previous_patch": (
                                  len(attempts) >= 2 and
                                  attempts[-1]["source_sha256"] ==
                                  attempts[-2]["source_sha256"]),
                              "model_tokens_so_far": reported_tokens,
                              "docker_public_calls_so_far": grader_calls}), flush=True)
            if public["status"].startswith(INFRA_STATUSES):
                report_arm["status"] = "grader_infrastructure_excluded"
                break
        if report_arm["status"] == "in_progress":
            report_arm["status"] = "completed"
        if "stop_reason" not in report_arm:
            report_arm["stop_reason"] = (
                "attempt_budget" if len(attempts) == 3 else "provider_or_grader_unavailable")
        report_arm["model_attempts"] = len(attempts)
        report_arm["model_provider_calls"] = provider_calls
        report_arm["model_calls_avoided"] = calls_avoided
        report_arm["provider_reported_tokens"] = reported_tokens
        report_arm["public_grader_calls"] = grader_calls
        report_arm["public_grader_reuses"] = grader_reuses
        _write_checkpoint(outfile, report)

    for arm in report["arms"]:
        if arm["status"] != "completed":
            arm["hidden_status"] = "not_checked_infrastructure_excluded"
            continue
        first = next((a for a in arm["attempts"] if a["public"]["passed"]), None)
        if first is None:
            arm["hidden_status"] = "not_checked_no_public_pass"
            arm["task_solved"] = False
        else:
            hidden = grader(task, mode="hidden", candidate=first["source"])
            arm["hidden_status"] = hidden["status"]
            arm["hidden_checks"] = hidden
            arm["task_solved"] = hidden["passed"] is True
            arm["hidden_selected_attempt"] = first["attempt_number"]
        _write_checkpoint(outfile, report)
    report["hidden_evaluated_after_arms"] = True
    report["status"] = "completed" if all(
        arm["status"] == "completed" for arm in report["arms"]) else "infrastructure_excluded"
    _write_checkpoint(outfile, report)
    print(json.dumps({
        "task": task["id"], "status": report["status"],
        "arms": [{
            "arm": x["arm"], "attempts": x["model_attempts"],
            "provider_calls": x["model_provider_calls"],
            "tokens": x["provider_reported_tokens"],
            "docker_public": x["public_grader_calls"],
            "docker_hidden": int(x.get("hidden_checks") is not None),
            "solved": x.get("task_solved"),
            "stop_reason": x["stop_reason"],
        } for x in report["arms"]]
    }), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-index", type=int, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(argv)
    result = run(task_index=args.task_index, cache_root=args.cache_root,
                 output_dir=args.output_dir, approve=args.approve)
    return 0 if result["status"] == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
