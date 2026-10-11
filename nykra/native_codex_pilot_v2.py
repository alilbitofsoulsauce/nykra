"""Post-hoc V2 follow-up: equal-budget AST-feedback retries in native Codex.

The V1 outcomes remain immutable. This module never rewrites V1 or changes
its scoring rules. Its two arms receive equivalent model/compiler/test
feedback; only the independently-rooted vs parent-revision instruction differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .coding_worker import validate_source
from .native_codex_pilot import (
    ALLOWED, MODEL, RUNNER, SCHEMA, score_source,
)
from .repair_tasks import TASKS, cases

PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "docs/evidence/v14_codex_pilot_protocol_v2.json"


def describe_validation(source: str) -> str | None:
    try:
        validate_source(source)
    except (SyntaxError, ValueError) as error:
        return type(error).__name__ + ": " + str(error)[:150]
    return None


def invoke(prompt: str, *, executable: Path, timeout: int) -> dict:
    """Return even invalid model source so both arms may repair it once."""
    start = time.monotonic()
    if not executable.is_file():
        return {"status": "model_binary_missing", "source": None,
                "elapsed_seconds": 0., "tokens_reported": None, "validation_error": None}
    with tempfile.TemporaryDirectory(prefix="nykra-codex-v2-") as directory:
        base = Path(directory)
        schema = base / "schema.json"
        outfile = base / "out.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        cmd = [
            str(executable), "exec", "--ignore-user-config",
            "--sandbox", "read-only", "--skip-git-repo-check",
            "--model", MODEL, "-c", 'approval_policy="never"',
            "-c", 'model_reasoning_effort="low"',
            "--output-schema", str(schema),
            "--output-last-message", str(outfile), prompt,
        ]
        try:
            result = subprocess.run(
                cmd, cwd=base, stdin=subprocess.DEVNULL,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "model_timeout", "source": None,
                    "elapsed_seconds": round(time.monotonic() - start, 2),
                    "tokens_reported": None, "validation_error": None}
        except OSError:
            return {"status": "model_start_failure", "source": None,
                    "elapsed_seconds": round(time.monotonic() - start, 2),
                    "tokens_reported": None, "validation_error": None}
        elapsed = round(time.monotonic() - start, 2)
        token_matches = re.findall(r"tokens used\s*\n([\d,]+)", result.stderr)
        tokens = int(token_matches[-1].replace(",", "")) if token_matches else None
        if result.returncode or not outfile.exists():
            return {"status": "model_failed", "source": None, "exit_code": result.returncode,
                    "elapsed_seconds": elapsed, "tokens_reported": tokens,
                    "validation_error": None}
        try:
            parsed = json.loads(outfile.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or set(parsed) != {"source"}:
                raise ValueError("invalid response keys")
            source = parsed["source"]
            if not isinstance(source, str) or len(source.encode("utf-8")) > 5000:
                raise ValueError("candidate size or type invalid")
        except (ValueError, UnicodeError, KeyError, TypeError):
            return {"status": "invalid_json_or_schema", "source": None,
                    "elapsed_seconds": elapsed, "tokens_reported": tokens,
                    "validation_error": "Invalid JSON or candidate payload"}
        error = describe_validation(source)
        return {
            "status": "ok" if error is None else "invalid_source",
            "source": source,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "elapsed_seconds": elapsed, "tokens_reported": tokens,
            "validation_error": error,
        }


def make_prompt(task: str, *, arm: str, previous: dict | None) -> str:
    spec = TASKS[task]
    first_three = [
        {"input": args, "expected": expected}
        for args, expected in cases(task, heldout=False)[:3]
    ]
    shared = (
        "Produce JSON with exactly one key 'source': a full Python "
        "def solve(...) implementation, no more than 4500 UTF-8 bytes. "
        "The evaluator allows no imports, attributes, method calls, classes, "
        "nested defs, decorators, while loops, try, with, or network/files. "
        "Use only for loops, indexing, slicing, conditionals, dictionaries, list "
        "concatenation and these direct builtin calls: " + ALLOWED +
        ". You may not invoke tools or inspect the local filesystem."
        "\nBUG TO REPAIR:\n" + spec["description"]
        + "\nBUGGY IMPLEMENTATION:\n" + spec["buggy_source"]
        + "\nTHREE PUBLIC SPEC EXAMPLES:\n" + json.dumps(first_three, ensure_ascii=False)
    )
    if previous is None:
        # Crucially both groups receive exactly the same first-attempt prompt.
        return shared + "\nImplement a corrected solve function. Return only JSON."
    feedback = previous["training"]
    shared += (
        "\nPREVIOUS PROPOSED SOURCE:\n" + (previous.get("source") or "(none returned)")
        + "\nCOMPILER OR VALIDATION ERROR:\n"
        + (previous.get("validation_error") or "none")
        + "\nPUBLIC TEST FEEDBACK (SAME IN BOTH ARMS):\n"
        + json.dumps({
            "status": feedback["status"], "passed": feedback["passed"],
            "total": feedback["total"],
            "failure_examples": feedback["failure_examples"],
        }, ensure_ascii=False)
    )
    if arm == "nykra":
        return shared + (
            "\nNYKRA POLICY: Revise the previous proposed source with the smallest "
            "repair that addresses validator/test failures and preserves working "
            "behavior. Return a complete implementation in JSON."
        )
    return shared + (
        "\nBASELINE POLICY: Solve again independently from the problem description. "
        "Use the same validator/test errors but construct a fresh implementation "
        "instead of incrementally editing the previous proposal. Return JSON."
    )


def evaluate_arm(task: str, arm: str, *, executable: Path, timeout: int) -> dict:
    attempts = []
    for index in (1, 2):
        parent = attempts[-1] if attempts else None
        if parent and parent["training"]["passed"] == parent["training"]["total"]:
            break
        prompt = make_prompt(task, arm=arm, previous=parent)
        proposed = invoke(prompt, executable=executable, timeout=timeout)
        source = proposed.get("source")
        if source is not None and proposed["status"] == "ok":
            training = score_source(task, source, heldout=False)
        else:
            training = {
                "status": proposed["status"], "passed": 0, "total": 14,
                "score": 0., "failure_examples": [],
            }
        attempts.append({
            **proposed, "training": training, "attempt_number": index,
            "parent_attempt": index - 1 if (arm == "nykra" and index > 1) else None,
        })
    # Deterministic selection on public train scores only, earlier attempt wins ties.
    scored = [
        attempt for attempt in attempts
        if attempt.get("source") is not None and attempt["status"] == "ok"
    ]
    chosen = max(scored, key=lambda a: (a["training"]["score"], -a["attempt_number"])) if scored else None
    final = score_source(task, chosen["source"], heldout=True) if chosen else {
        "status": "no_valid_candidate", "passed": 0, "total": 32,
        "score": 0., "failure_examples": [],
    }
    return {
        "task": task, "arm": arm, "attempt_budget": 2,
        "attempts_used": len(attempts), "best_attempt": chosen["attempt_number"] if chosen else None,
        "final_training_passed": chosen["training"]["passed"] if chosen else 0,
        "final_heldout_passed": final["passed"],
        "final_heldout_total": final["total"],
        "final_heldout_success": final["score"] == 1.,
        "total_tokens_reported": sum(x.get("tokens_reported") or 0 for x in attempts),
        "token_reporting_complete": all(x.get("tokens_reported") is not None for x in attempts),
        "total_wall_seconds": round(sum(x["elapsed_seconds"] for x in attempts), 2),
        "attempts": attempts,
    }


def execute_task(task: str, output: Path, *, approval: bool = False) -> dict:
    if approval is not True:
        raise ValueError("explicit approval needed for model execution")
    raw_protocol = PROTOCOL_PATH.read_bytes()
    protocol = json.loads(raw_protocol)
    if protocol.get("protocol_id") != "nykra-native-codex-matched-pilot-v2":
        raise ValueError("unexpected protocol")
    if protocol.get("model") != MODEL or protocol.get("attempt_limit_per_task_arm") != 2:
        raise ValueError("model or budget does not match fixed protocol")
    order = next((x["run_order"] for x in protocol["task_order"] if x["task"] == task), None)
    if order is None or sorted(order) != ["baseline", "nykra"]:
        raise ValueError("unregistered task")
    if output.exists():
        raise ValueError("refuse overwrite of previous trial")
    output.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "protocol_id": protocol["protocol_id"], "task": task, "model": MODEL,
        "protocol_sha256": hashlib.sha256(raw_protocol).hexdigest(),
        "arm_order": order, "status": "in_progress", "arms": [],
        "limitations": "post-hoc n=4, function-level rather than SWE-bench, no blind task authoring",
    }
    def checkpoint():
        tmp = output.with_suffix(".part.json")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, output)
    checkpoint()
    for arm in order:
        result = evaluate_arm(task, arm, executable=RUNNER,
                              timeout=int(protocol["run_timeout_seconds"]))
        state["arms"].append(result)
        checkpoint()
    state["status"] = "completed"
    checkpoint()
    return state


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--task", choices=tuple(TASKS), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--approve", action="store_true")
    args = p.parse_args()
    result = execute_task(args.task, args.out, approval=args.approve)
    for arm in result["arms"]:
        print(result["task"], arm["arm"], arm["attempts_used"],
              arm["final_heldout_passed"], "/", arm["final_heldout_total"])
