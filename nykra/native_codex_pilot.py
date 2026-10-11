"""Bounded real Codex model trial: fresh roots vs Nykra depth revisions.

A *small exploratory* function-level code repair study, not SWE-bench.
All task definitions, order and limits come from the frozen protocol JSON.
The connected model never receives held-out fixtures or evaluator sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .coding_worker import validate_source
from .repair_tasks import TASKS, cases

MODEL = "gpt-6-luna"
RUNNER = (
    Path.home() / "AppData/Local/Nykra/model-runners/"
    "codex-official-v0.160/release/codex-x86_64-pc-windows-msvc.exe"
)
ALLOWED = (
    "abs, all, any, bool, dict, enumerate, int, len, list, max, min, "
    "range, reversed, set, sorted, str, sum, tuple, zip"
)
SCHEMA = {
    "type": "object", "properties": {"source": {"type": "string"}},
    "required": ["source"], "additionalProperties": False,
}


def score_source(task: str, source: str, *, heldout: bool) -> dict:
    points = cases(task, heldout=heldout)
    try:
        validate_source(source)
    except (SyntaxError, ValueError):
        return {"status": "invalid_source", "passed": 0, "total": len(points),
                "score": 0.0, "failure_examples": []}
    script = Path(__file__).with_name("coding_worker.py").resolve()
    request = json.dumps({"source": source, "inputs": [x for x, _ in points]})
    environment = {key: val for key, val in os.environ.items()
                   if key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR")}
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        with tempfile.TemporaryDirectory(prefix="nykra-pilot-worker-") as directory:
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(script)], input=request,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=directory, env=environment,
                timeout=8, check=False,
            )
        if process.returncode != 0 or len(process.stdout) > 100000:
            raise RuntimeError("worker_failed")
        actual = json.loads(process.stdout)["outputs"]
        if not isinstance(actual, list) or len(actual) != len(points):
            raise RuntimeError("invalid_worker_response")
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError, RuntimeError):
        return {"status": "worker_error", "passed": 0, "total": len(points),
                "score": 0.0, "failure_examples": []}
    passed = 0
    examples = []
    for (arguments, expected), found in zip(points, actual):
        success = isinstance(found, dict) and "value" in found and found["value"] == expected
        if success:
            passed += 1
        elif not heldout and len(examples) < 3:
            examples.append({
                "input": arguments, "expected": expected,
                "actual": found.get("value", "candidate_exception") if isinstance(found, dict)
                          else "invalid_output",
            })
    return {
        "status": "ok", "passed": passed, "total": len(points),
        "score": passed / len(points),
        "failure_examples": examples if not heldout else [],
    }


def prompt_for(task: str, *, previous: str | None = None,
               training: dict | None = None, guided: bool = False) -> str:
    info = TASKS[task]
    public = [{"input": inp, "expected": out}
              for inp, out in cases(task, heldout=False)[:3]]
    common = (
        "Fix the specified Python function bug. You must return a JSON object "
        'with ONLY the key "source", containing exactly one full def solve(...) '
        "function of no more than 4500 UTF-8 bytes. Do not use imports, classes, "
        "nested functions, decorators, attribute access, method calls, while "
        "loops, global variables or file/network IO. Permitted builtins are: "
        + ALLOWED + ". Slicing, for loops, dictionaries and list concatenation "
        "are allowed. Do not read or call tools; use only the supplied information."
        "\nTASK:\n" + info["description"]
        + "\nORIGINAL BUGGY SOURCE:\n" + info["buggy_source"]
        + "\nTHREE PUBLIC EXAMPLES:\n" + json.dumps(public, ensure_ascii=False)
    )
    if previous is None:
        return common + "\nProduce your first corrected solution now."
    feedback = json.dumps({
        "passed": training["passed"], "total": training["total"],
        "failure_examples": training["failure_examples"],
    }, ensure_ascii=False)
    # Both arms receive *identical* previous source and measured feedback.
    common += "\nPREVIOUS EVALUATED SOURCE:\n" + previous
    common += "\nSAME PUBLIC TRAINING FEEDBACK AVAILABLE TO EITHER ARM:\n" + feedback
    if guided:
        return common + "\nNYKRA EXPLORATION POLICY: Revise the previous best tested source; repair the specific failing cases while preserving successful behavior. Return the complete revised function."
    return common + "\nBASELINE EXPLORATION POLICY: Generate a fresh, independent solution from the specification rather than making an incremental edit. Use the same feedback to avoid past errors. Return the complete function."


def invoke_model(prompt: str, *, executable: Path, timeout: int) -> dict:
    if not executable.is_file():
        return {"status": "model_binary_missing", "elapsed_seconds": 0.0,
                "source": None, "tokens_reported": None}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-codex-pilot-") as directory:
        root = Path(directory)
        schema_path = root / "schema.json"
        last_path = root / "candidate.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        command = [
            str(executable), "exec", "--ignore-user-config",
            "--sandbox", "read-only", "--skip-git-repo-check",
            "--model", MODEL, "-c", 'approval_policy="never"',
            "-c", 'model_reasoning_effort="low"',
            "--output-schema", str(schema_path),
            "--output-last-message", str(last_path), prompt,
        ]
        try:
            result = subprocess.run(
                command, cwd=root, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "model_timeout",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "source": None, "tokens_reported": None}
        except OSError:
            return {"status": "model_start_failure",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "source": None, "tokens_reported": None}
        elapsed = round(time.monotonic() - started, 2)
        tokens = re.findall(r"tokens used\s*\n([\d,]+)", result.stderr)
        tokens_used = int(tokens[-1].replace(",", "")) if tokens else None
        if result.returncode != 0 or not last_path.is_file():
            # No credential details, tokens or raw stderr are persisted.
            return {"status": "model_failed", "exit_code": result.returncode,
                    "elapsed_seconds": elapsed, "source": None,
                    "tokens_reported": tokens_used}
        try:
            parsed = json.loads(last_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or set(parsed) != {"source"}:
                raise ValueError("invalid_response_keys")
            source = parsed["source"]
            validate_source(source)
        except (ValueError, SyntaxError, UnicodeError, KeyError, TypeError):
            return {"status": "invalid_model_output",
                    "elapsed_seconds": elapsed, "source": None,
                    "tokens_reported": tokens_used}
    return {"status": "ok", "elapsed_seconds": elapsed,
            "source": source, "tokens_reported": tokens_used,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}


def run_arm(task: str, arm: str, *, executable: Path, timeout: int) -> dict:
    attempts = []
    guided = arm == "nykra"
    for number in (1, 2):
        parent = attempts[-1] if attempts else None
        if parent is not None and parent["training"]["passed"] == parent["training"]["total"]:
            break
        prompt = prompt_for(
            task, previous=parent.get("source") if parent else None,
            training=parent.get("training") if parent else None, guided=guided,
        )
        output = invoke_model(prompt, executable=executable, timeout=timeout)
        source = output.get("source")
        training = score_source(task, source, heldout=False) if source is not None else {
            "status": "no_candidate", "passed": 0, "total": 14, "score": 0.0,
            "failure_examples": [],
        }
        attempts.append({
            **output, "training": training, "attempt_number": number,
            "parent_attempt": number - 1 if guided and number > 1 else None,
        })
        if source is None:
            break
    best = max(attempts, key=lambda x: (x["training"]["score"], -x["attempt_number"]))
    selected = best["source"]
    heldout = score_source(task, selected, heldout=True) if selected is not None else {
        "status": "no_candidate", "passed": 0, "total": 32, "score": 0.0, "failure_examples": [],
    }
    return {
        "arm": arm, "task": task,
        "attempt_budget": 2, "attempts_used": len(attempts),
        "time_seconds": round(sum(x["elapsed_seconds"] for x in attempts), 2),
        "tokens_reported": sum(x["tokens_reported"] or 0 for x in attempts),
        "tokens_reporting_complete": all(x["tokens_reported"] is not None for x in attempts),
        "best_attempt_number": best["attempt_number"],
        "final_training_passed": best["training"]["passed"],
        "final_heldout_passed": heldout["passed"],
        "final_heldout_total": heldout["total"],
        "final_heldout_success": heldout["score"] == 1.0,
        "heldout_score": heldout["score"],
        "attempts": attempts,
    }


def run_task(task: str, *, output: Path, approval: bool = False) -> dict:
    if approval is not True:
        raise ValueError("explicit approval required")
    repo = Path(__file__).resolve().parents[1]
    protocol_file = repo / "docs/evidence/v14_codex_pilot_protocol.json"
    protocol_bytes = protocol_file.read_bytes()
    protocol = json.loads(protocol_bytes)
    if task not in TASKS:
        raise ValueError("task outside preregistered suite")
    order = next((x["run_order"] for x in protocol["task_order"] if x["task"] == task), None)
    if order is None or sorted(order) != ["baseline", "nykra"]:
        raise ValueError("task order is absent or malformed")
    if (protocol["model"] != MODEL or protocol["attempt_limit_per_task_arm"] != 2
            or protocol["training_examples_per_task"] != 14
            or protocol["heldout_examples_per_task"] != 32):
        raise ValueError("protocol mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("task evidence already exists; refusing overwrite")
    record = {
        "protocol_id": protocol["protocol_id"], "model": MODEL,
        "task": task,
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "arm_order": order,
        "runner": "codex-cli-0.160.0-chatgpt-auth",
        "reasoning_effort": "low",
        "training_hidden_disjoint": True,
        "task_scope": "local function-level bug repair; not SWE-bench",
        "status": "in_progress", "arms": [],
    }
    # Persist even partial runs, including timeout/invalid-output arm outcomes.
    def checkpoint():
        interim = output.with_suffix(".part.json")
        interim.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(interim, output)
    checkpoint()
    for arm in order:
        answer = run_arm(task, arm, executable=RUNNER,
                         timeout=int(protocol["run_timeout_seconds"]))
        record["arms"].append(answer)
        checkpoint()
    record["status"] = "completed"
    checkpoint()
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=tuple(TASKS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    outcome = run_task(args.task, output=args.out, approval=args.approve)
    for arm in outcome["arms"]:
        print(outcome["task"], arm["arm"], arm["attempts_used"],
              arm["final_heldout_passed"], "/", arm["final_heldout_total"])
