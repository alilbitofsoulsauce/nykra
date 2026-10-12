"""Offline verification/aggregation of the pre-registered v0.31 paired study.

This script reads immutable raw external-model receipts, confirms each arm had
its own provider completions and correct public/hidden sequencing, and records
real inference/token/Docker counts without claiming adaptive accuracy uplift.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_FILE = ROOT / "docs/evidence/v31_live_study_protocol.json"
PROTOCOL_SHA = "d50af1b42f21ebf0361a315d37fe822abe992bd5a32d88dac32cc6461f951f24"
RUNS = ROOT / "docs/evidence/v31_live_issues"
SUMMARY = ROOT / "docs/evidence/v31_live_efficiency_summary.json"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def summarize():
    original = PROTOCOL_FILE.read_bytes()
    if hashlib.sha256(original).hexdigest() != PROTOCOL_SHA:
        raise ValueError("v31 frozen study protocol changed")
    protocol = json.loads(original)
    stats = {
        name: {
            "hidden_verified_tasks_solved": 0,
            "model_attempts": 0,
            "actual_provider_calls": 0,
            "avoided_provider_calls": 0,
            "provider_reported_tokens": 0,
            "public_docker_evaluations": 0,
            "public_docker_evaluations_reused": 0,
            "hidden_docker_grading_sessions": 0,
            "early_halts": 0,
        } for name in protocol["arms"]
    }
    seen_provider_responses = set()
    tasks = []
    for frozen in protocol["tasks"]:
        task_id = frozen["id"]
        source = RUNS / (task_id + ".json")
        raw = source.read_bytes()
        trial = json.loads(raw)
        if (trial["status"] != "completed" or
                trial["frozen_protocol_sha256"] != PROTOCOL_SHA or
                trial["task_id"] != task_id or
                not trial["hidden_evaluated_after_arms"] or
                len(trial["arms"]) != 2):
            raise ValueError("incomplete or incomparable study run: " + task_id)
        arms = {a["arm"]: a for a in trial["arms"]}
        if set(arms) != set(protocol["arms"]):
            raise ValueError("arm identity mismatch")
        if [a["arm"] for a in trial["arms"]] != protocol["arm_execution_order_by_task"][
                protocol["task_order"].index(task_id)]:
            raise ValueError("arm ordering changed from protocol")
        first_hashes = {a["attempts"][0]["prompt_sha256"] for a in arms.values()
                        if a["attempts"]}
        if len(first_hashes) != 1:
            raise ValueError("arms did not get matched identical first prompts")
        taskrow = {
            "task": task_id, "project": frozen["project"],
            "buggy_commit": frozen["buggy_commit"],
            "raw_evidence_file": "docs/evidence/v31_live_issues/" + task_id + ".json",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "hidden_reference_prevalidated_before_inference": frozen[
                "reference_preflight_eligible"],
            "arms": {},
        }
        for name in protocol["arms"]:
            arm = arms[name]
            if arm["status"] != "completed":
                raise ValueError("excluded infrastructure arm " + task_id)
            trials = arm["attempts"]
            budget = protocol["budget_model_calls_per_arm_per_task"]
            if not 1 <= len(trials) <= budget:
                raise ValueError("attempt budget inconsistency")
            local_ids = set()
            count_model_calls = 0
            tokens = 0
            true_evaluations = 0
            public_reused = 0
            successes = []
            hash_indices = {}
            for i, step in enumerate(trials, 1):
                if step["attempt_number"] != i or digest(step["source"]) != step["source_sha256"]:
                    raise ValueError("invalid persisted candidate SHA")
                if digest(step["model_raw_output"]) != step["model_raw_output_sha256"]:
                    raise ValueError("invalid persisted model output SHA")
                rid = step["model_response_id"]
                if not isinstance(rid, str) or not rid or rid in seen_provider_responses:
                    raise ValueError("missing/duplicate provider response IDs across arms")
                seen_provider_responses.add(rid)
                local_ids.add(rid)
                usage = step["model_provider_reported_tokens"]
                if not all(type(usage.get(x)) is int and usage[x] >= 0
                           for x in ("prompt_tokens", "completion_tokens", "total_tokens")):
                    raise ValueError("missing valid provider token usage")
                if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                    raise ValueError("provider usage not additive")
                if step["model_provider_reported_cost"] != 0:
                    raise ValueError("this study expected provider reported cost zero")
                if step["model_cache_hit"]:
                    raise ValueError("unexpected exact-request hit; handle separately")
                count_model_calls += 1
                tokens += usage["total_tokens"]
                if step["public_grade_reused"]:
                    public_reused += 1
                    previous = step["public_grade_source_attempt"]
                    if (name != "nykra_optimized_depth" or
                            type(previous) is not int or previous not in hash_indices
                            or hash_indices[previous] != step["source_sha256"] or
                            trials[previous-1]["public"]["status"] != "test_failed" or
                            step["public"] != trials[previous-1]["public"]):
                        raise ValueError("public Docker replay has no identical failing origin")
                elif step["public"]["status"] in ("test_failed", "ok"):
                    true_evaluations += 1
                if step["public"]["passed"]:
                    successes.append(step)
                hash_indices[i] = step["source_sha256"]
            if count_model_calls != arm["model_provider_calls"]:
                raise ValueError("provider-call counts disagree")
            if tokens != arm["provider_reported_tokens"]:
                raise ValueError("reported tokens disagree")
            if true_evaluations != arm["public_grader_calls"] or (
                    public_reused != arm["public_grader_reuses"]):
                raise ValueError("public evaluation counts disagree")
            if arm["model_calls_avoided"] != 0:
                raise ValueError("unexpected provider-call cache in this cohort")
            hidden = arm["hidden_status"]
            solved = arm["task_solved"]
            if successes:
                if (hidden not in ("ok", "test_failed") or
                        not arm.get("hidden_checks") or
                        solved is not (hidden == "ok")):
                    raise ValueError("missing independently graded success")
            elif hidden != "not_checked_no_public_pass" or solved:
                raise ValueError("hidden grading leaked or public success inflated")
            if name == "baseline_depth" and public_reused:
                raise ValueError("baseline unexpectedly received public cache")
            stat = stats[name]
            stat["hidden_verified_tasks_solved"] += int(solved)
            stat["model_attempts"] += len(trials)
            stat["actual_provider_calls"] += count_model_calls
            stat["avoided_provider_calls"] += arm["model_calls_avoided"]
            stat["provider_reported_tokens"] += tokens
            stat["public_docker_evaluations"] += true_evaluations
            stat["public_docker_evaluations_reused"] += public_reused
            stat["hidden_docker_grading_sessions"] += int(bool(successes))
            stat["early_halts"] += int(arm["stop_reason"] == "paused_repeated_failed_patch")
            taskrow["arms"][name] = {
                "model_calls": count_model_calls,
                "provider_tokens": tokens,
                "public_docker_evaluations": true_evaluations,
                "public_docker_reuses": public_reused,
                "hidden_verdict": hidden,
                "task_solved": solved,
                "stop_reason": arm["stop_reason"],
                "model_output_sha256": [x["model_raw_output_sha256"] for x in trials],
                "candidate_source_sha256": [x["source_sha256"] for x in trials],
                "public_grade_status": [x["public"]["status"] for x in trials],
            }
        tasks.append(taskrow)
    b, o = stats["baseline_depth"], stats["nykra_optimized_depth"]
    return {
        "schema": "nykra-v31-independent-live-historical-issue-comparison-v1",
        "protocol_sha256": PROTOCOL_SHA,
        "status": "completed",
        "task_count": len(tasks),
        "historical_projects": sorted({r["project"] for r in tasks}),
        "prior_issue_reuse": True,
        "model": protocol["model"],
        "independent_model_calls_per_arm": True,
        "identical_first_prompt_per_issue": True,
        "heldout_feedback_never_passed_to_model": True,
        "reporting_units": "three paired historical issue instances, not independent attempts",
        "arms": stats,
        "comparisons": {
            "hidden_verified_success_difference_optimized_minus_baseline":
                o["hidden_verified_tasks_solved"] - b["hidden_verified_tasks_solved"],
            "public_docker_evaluations_avoided":
                b["public_docker_evaluations"] - o["public_docker_evaluations"],
            "public_docker_avoidance_fraction":
                ((b["public_docker_evaluations"]-o["public_docker_evaluations"]) /
                 b["public_docker_evaluations"]),
            "actual_provider_call_difference":
                b["actual_provider_calls"] - o["actual_provider_calls"],
            "provider_reported_token_difference_baseline_minus_optimized":
                b["provider_reported_tokens"] - o["provider_reported_tokens"],
        },
        "causal_coding_accuracy_uplift_proven": False,
        "claim_limits": [
            "Prior Nykra-studied historical BugsInPy tasks, not unseen issues.",
            "Only three issues across two projects; no statistical power.",
            "One deliberately fixed low-capacity free model and one run per arm.",
            "Both arms use depth, so this isolates operational optimizations and not adaptive exploration.",
            "Exact request caching and two-failure early-stop had no cache hit/halt in this cohort.",
            "Unusual same-content independent inference may reflect model/provider determinism.",
            "No improvement in task success or model tokens was observed.",
            "Separate public and hidden Docker graders inherit the limitations of earlier historical suites.",
        ],
        "tasks": tasks,
    }


def main():
    if SUMMARY.exists():
        raise ValueError("refusing to overwrite frozen v31 study summary")
    report = summarize()
    SUMMARY.write_text(json.dumps(report, indent=2)+"\n",
                       encoding="utf-8", newline="\n")
    print(json.dumps({
        "task_count": report["task_count"],
        "arms": report["arms"],
        "comparisons": report["comparisons"],
        "summary_path": str(SUMMARY),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
