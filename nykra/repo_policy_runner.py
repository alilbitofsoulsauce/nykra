"""Codex repository exploration using Nykra's actual shared ancestry policy.

Restricted to the project's explicitly enumerated *trusted* local Nykra
regression fixtures. Never point this at untrusted external repositories:
Python grading is not a hardened sandbox. This runner is experimental and
does NOT retroactively change any v0.15 evidence or read hidden test answers
during proposal generation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .exploration_policy import select_next
from .repository_repair_trial import (
    extract_function, grade, invoke_codex, model_prompt,
    prepare_repository, protocol, replace_function,
)

Response = dict
ModelProposer = Callable[[str, int], Response]


def explore_repo(
    task: dict, repo: Path, *, policy: str, budget: int = 4,
    timeout: int = 70, proposer: ModelProposer | None = None,
) -> dict:
    """Request candidates by the *same* policy used by IterativeCoding.

    The model is responsible for proposing code; only the trusted host may
    apply it to the disposable Git checkout. No model permissions or hidden
    grading are exposed by this function.
    """
    if proposer is None:
        proposer = lambda prompt, seconds: invoke_codex(prompt, timeout=seconds)
    module = repo / task["file"]
    original = module.read_text(encoding="utf-8")
    broken = extract_function(original, task["function"])
    evaluations = []
    state = []
    while True:
        request = select_next(policy=policy, steps=state, budget=budget, threshold=1.0)
        if request is None:
            break
        selected = next((attempt for attempt in evaluations
                         if attempt["attempt_id"] == request["parent_attempt_id"]), None)
        previous = None
        if selected is not None:
            previous = {
                "source": selected.get("source"), "public": selected["public"],
                "error": selected.get("error"),
            }
        prompt = model_prompt(task, broken, prev=previous, arm="nykra")
        if request["kind"] == "new_root" and state:
            prompt += (
                "\nEXPLORATION BRANCH: Start a new independent root from the original "
                "bug report. Do not assume the latest attempt is the parent."
            )
        returned = proposer(prompt, timeout)
        source = returned.get("source")
        err = None
        if returned.get("status") != "ok" or not isinstance(source, str):
            public = {
                "passed": 0, "total": 7, "score": 0.,
                "status": "model_unavailable", "failed_public": [],
            }
        else:
            try:
                module.write_text(replace_function(original, task["function"], source),
                                  encoding="utf-8")
                public = grade(repo, task, heldout=False)
            except (SyntaxError, ValueError, UnicodeError) as ex:
                err = type(ex).__name__ + ": " + str(ex)[:160]
                public = {
                    "passed": 0, "total": 7, "score": 0.,
                    "status": "patch_invalid", "failed_public": [],
                }
            finally:
                module.write_text(original, encoding="utf-8")
        index = len(state)
        id_ = "attempt-" + str(index + 1)
        state.append({
            "id": id_, "position": index, "score": public["score"],
            "parent_id": request["parent_attempt_id"],
        })
        evaluations.append({
            "attempt_id": id_, "source": source,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()
                             if isinstance(source, str) else None,
            "kind": request["kind"], "parent_attempt_id": request["parent_attempt_id"],
            "public": public, "error": err,
            "status": returned.get("status"),
            "model_seconds": returned.get("seconds", 0),
            "model_tokens": returned.get("tokens"),
        })
    # Holdout evaluated ONCE, after choosing best public-scored proposal.
    eligible = [a for a in evaluations if isinstance(a["source"], str)
                and a["public"]["status"] == "ok"]
    best = max(eligible, key=lambda a: (a["public"]["score"],
               -int(a["attempt_id"].split("-")[1]))) if eligible else None
    if best is not None:
        try:
            module.write_text(replace_function(original, task["function"], best["source"]),
                              encoding="utf-8")
            heldout = grade(repo, task, heldout=True)
        finally:
            module.write_text(original, encoding="utf-8")
    else:
        heldout = {"passed": 0, "total": 26, "score": 0., "status": "no_candidate"}
    return {
        "task_id": task["id"], "policy": policy, "budget": budget,
        "evaluations_used": len(evaluations),
        "heldout_passed": heldout["passed"],
        "heldout_total": heldout["total"],
        "heldout_success": heldout["score"] == 1.,
        "best_attempt_id": best["attempt_id"] if best else None,
        "candidate_attempts": evaluations,
        "qualification": "trusted synthetic Nykra source regression; not a real external issue benchmark",
    }


def run_trusted_fixture(task_id: str, *, policy: str = "adaptive", budget: int = 4,
                        approval: bool = False) -> dict:
    if approval is not True:
        raise ValueError("explicit authorization required before model calls or code evaluation")
    tasks = protocol()["tasks"]
    task = next((x for x in tasks if x["id"] == task_id), None)
    if task is None:
        raise ValueError("only enumerated trusted Nykra regression tasks are supported")
    if type(budget) is not int or not 1 <= budget <= 8:
        raise ValueError("attempt budget must be 1..8")
    with tempfile.TemporaryDirectory(prefix="nykra-policy-source-") as directory:
        workspace = prepare_repository(task, Path(directory), mutate=True)
        return explore_repo(task, workspace, policy=policy, budget=budget)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True,
                        choices=[t["id"] for t in protocol()["tasks"]])
    parser.add_argument("--policy", default="adaptive",
                        choices=("breadth", "depth", "adaptive"))
    parser.add_argument("--budget", default=4, type=int)
    parser.add_argument("--approve", action="store_true")
    options = parser.parse_args()
    print(json.dumps(run_trusted_fixture(
        options.task, policy=options.policy,
        budget=options.budget, approval=options.approve,
    ), indent=2))
