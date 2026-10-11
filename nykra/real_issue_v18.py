"""Nykra v0.18 controlled, cross-repository real-issue repair pilot.

This is not the official BugsInPy evaluation harness. Upstream code is only
executed inside constrained disposable offline Docker containers. Independent
hidden checks are never sent to the model and execute once per selected arm.
Host CLI operations (git and docker) are trusted; this is NOT a certified VM
sandbox against hostile code or a verified agent-agnostic model uplift study.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid

from .exploration_policy import select_next
from .repository_repair_trial import extract_function, replace_function, invoke_codex
from .v18_hidden_spec import HIDDEN_TEST_MODULES

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/evidence/v18_protocol.json"
DATASET = ROOT / "experiments/bugsinpy-source"
REPOS = {
    "youtube-dl": ROOT / "experiments/bench-source/youtube-dl",
    "PySnooper": ROOT / "experiments/bench-source/pysnooper",
}
MAX_ARCHIVE_BYTES = 22_000_000
MAX_PATCH_BYTES = 16000


def manifest():
    raw = PROTOCOL.read_bytes()
    doc = json.loads(raw)
    if doc["schema"] != "nykra-real-repair-independent-v18":
        raise ValueError("protocol id mismatch")
    if doc["model"] != "gpt-6-luna":
        raise ValueError("model mismatch")
    if doc["hidden_spec_sha256"] != hashlib.sha256(
            Path(__file__).with_name("v18_hidden_spec.py").read_bytes()).hexdigest():
        raise ValueError("frozen hidden test source has changed")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", doc["image_id"]):
        raise ValueError("unlocked image")
    return doc, hashlib.sha256(raw).hexdigest()


def source_bytes(task, commit, filename):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("invalid Git commit")
    if filename not in (task["source_file"], task["test_file"]):
        raise ValueError("file outside task allowlist")
    r = subprocess.run(["git", "show", commit + ":" + filename],
                       cwd=REPOS[task["project"]], capture_output=True, timeout=35)
    if r.returncode:
        raise RuntimeError("pinned Git source unavailable")
    return r.stdout


def export_buggy_commit(task, dest):
    source_repo = REPOS[task["project"]]
    commit = task["buggy_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("bad commit")
    r = subprocess.run(["git", "archive", "--format=tar", commit], cwd=source_repo,
                       capture_output=True, timeout=90)
    if r.returncode or len(r.stdout) > MAX_ARCHIVE_BYTES:
        raise ValueError("unavailable or oversized pinned source")
    with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:") as tar:
        total = 0
        for entry in tar:
            p = Path(entry.name.replace("\\", "/"))
            if p.is_absolute() or ".." in p.parts or not (
                    entry.isfile() or entry.isdir()):
                raise ValueError("unsafe upstream archive member")
            target = dest / p
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                total += entry.size
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("too much extracted source")
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(entry) as src, target.open("wb") as sink:
                    shutil.copyfileobj(src, sink)


def build_context(task, dest, image, *, replacement=None):
    export_buggy_commit(task, dest)
    fixed_test = source_bytes(task, task["fixed_commit"], task["test_file"])
    test_path = dest / task["test_file"]
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_bytes(fixed_test)
    fixture = HIDDEN_TEST_MODULES[task["id"]]
    (dest / "_nykra_private_checks.py").write_text(fixture, encoding="utf-8")
    if replacement is not None:
        file = dest / task["source_file"]
        original = file.read_text(encoding="utf-8")
        file.write_text(replace_function(original, task["function"], replacement),
                        encoding="utf-8")
    # Do not execute upstream setup scripts, Dockerfiles, hooks or install commands.
    (dest / "Dockerfile.nykra").write_text(
        "FROM " + image + "\n"
        "COPY . /repo/\nWORKDIR /repo\n"
        "ENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\n"
        "USER 65534:65534\n", encoding="utf-8")
    (dest / ".dockerignore").write_text(
        ".git\n.env\n.env.*\n**/__pycache__\n**/*.pyc\n", encoding="utf-8")


def _test_commands(task, mode):
    if mode == "public":
        if task["project"] == "youtube-dl":
            return [["-B", "-m", "unittest", "-q", task["public_test"]]]
        return [["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 task["public_test"]]]
    if mode != "hidden":
        raise ValueError("unknown verification mode")
    commands = [["-B", "-m", "unittest", "-q", "_nykra_private_checks"]]
    if task["project"] == "PySnooper":
        commands.append(["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         *task["hidden_upstream_tests"]])
    else:
        commands.append(["-B", "-m", "unittest", "-q",
                         *task["hidden_upstream_tests"]])
    return commands


def grade(task, *, mode, candidate=None):
    """Return pass/fail only; no hidden output to model or iteration policy."""
    started = time.monotonic()
    doc, _ = manifest()
    if candidate is not None and (not isinstance(candidate, str) or
            len(candidate.encode("utf-8")) > MAX_PATCH_BYTES):
        return {"status": "invalid_patch", "passed": False}
    tag = "nykra-v18-" + uuid.uuid4().hex[:16]
    built = False
    with tempfile.TemporaryDirectory(prefix="nykra-v18-context-") as directory:
        root = Path(directory)
        try:
            pinned_tag = "nykra-py38-pytest:v18b"
            base_check = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", pinned_tag],
                capture_output=True, timeout=12)
            if (base_check.returncode or
                    base_check.stdout.decode("ascii", "replace").strip() != doc["image_id"]):
                return {"status": "base_image_mismatch", "passed": False}
            # BuildKit requires a resolvable local name in FROM. Verify its
            # immutable image ID matches the frozen protocol before building.
            build_context(task, root, pinned_tag, replacement=candidate)
            build = subprocess.run(
                ["docker", "build", "--pull=false", "--network", "none",
                 "-f", str(root / "Dockerfile.nykra"), "-t", tag, str(root)],
                capture_output=True, timeout=90)
            if build.returncode:
                return {"status": "build_error", "passed": False}
            built = True
            image_result = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
                capture_output=True, timeout=12)
            image = image_result.stdout.decode("ascii", errors="replace").strip()
            if image_result.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                return {"status": "image_mismatch", "passed": False}
            records = []
            for cmd in _test_commands(task, mode):
                args = ["docker", "run", "--rm", "--pull", "never",
                        "--network", "none", "--read-only", "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges", "--pids-limit", "64",
                        "--memory", "384m", "--memory-swap", "384m", "--cpus", "1",
                        "--user", "65534:65534",
                        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=48m",
                        "--workdir", "/repo",
                        "--env", "PYTHONPATH=/repo", "--env", "HOME=/tmp",
                        "--env", "PYTHONDONTWRITEBYTECODE=1",
                        "--entrypoint", "python", image, *cmd]
                try:
                    run = subprocess.run(args, capture_output=True, timeout=42)
                    status = "ok" if run.returncode == 0 else "test_failed"
                    records.append({"status": status, "exit_code": run.returncode,
                                    "stderr_sha256": hashlib.sha256(run.stderr).hexdigest(),
                                    "stdout_sha256": hashlib.sha256(run.stdout).hexdigest()})
                except subprocess.TimeoutExpired:
                    records.append({"status": "timeout"})
                    break
            if all(x["status"] == "ok" for x in records) and len(records) == len(_test_commands(task, mode)):
                status = "ok"
            elif any(x["status"] == "timeout" for x in records):
                status = "timeout"
            else:
                status = "test_failed"
            return {"status": status, "passed": status == "ok", "checks": records,
                    "mode": mode, "elapsed_seconds": round(time.monotonic()-started,2)}
        except (OSError, RuntimeError, ValueError, SyntaxError, UnicodeError,
                subprocess.TimeoutExpired, KeyError) as e:
            return {"status": "setup_error", "passed": False,
                    "error_type": type(e).__name__}
        finally:
            if built:
                try:
                    subprocess.run(["docker", "image", "rm", "-f", tag],
                                   capture_output=True, timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    pass


def prevalidate(task):
    source = source_bytes(task, task["fixed_commit"], task["source_file"]).decode("utf-8")
    reference = extract_function(source, task["function"])
    public_bug = grade(task, mode="public")
    public_fixed = grade(task, mode="public", candidate=reference)
    hidden_bug = grade(task, mode="hidden")
    hidden_fixed = grade(task, mode="hidden", candidate=reference)
    eligible = (public_bug["status"] == "test_failed"
                and public_fixed["status"] == "ok"
                and hidden_bug["status"] == "test_failed"
                and hidden_fixed["status"] == "ok")
    return {"public_buggy": public_bug, "public_reference": public_fixed,
            "hidden_buggy": hidden_bug, "hidden_reference": hidden_fixed,
            "eligible": eligible}


def prompt(task, broken, *, parent=None, new_root=False):
    # Strictly no hidden paths, source, fixtures or test outcomes in prompts.
    p = (
        "Repair a real historical Python bug in project " + task["project"] +
        '. Return exactly one JSON object {"source": "full top-level function text"}. '
        "Preserve the function's public signature and module imports. "
        "No external tools or web lookup; use only the issue and source below.\n"
        "ISSUE: " + task["issue"] + "\nFUNCTION: " + task["function"] +
        "\nBUGGY FUNCTION:\n" + broken
    )
    if parent is None:
        return p + "\nWrite a correct independent solution."
    p += ("\nEVALUATED PARENT SOURCE:\n" + (parent.get("source") or "<invalid>") +
          "\nPUBLIC REGRESSION RESULT:\n" +
          json.dumps({"status": parent["public"]["status"],
                      "passed": parent["public"]["passed"]}))
    if new_root:
        return p + "\nThe exploration policy selected a fresh independent root; rethink from the issue."
    return p + "\nRevise the selected previous candidate based on public feedback."


def run_arm(task, arm, *, proposer=None):
    if arm not in ("baseline", "nykra"):
        raise ValueError("unknown arm")
    doc, _ = manifest()
    broken = extract_function(
        source_bytes(task, task["buggy_commit"], task["source_file"]).decode("utf-8"),
        task["function"])
    attempts = []
    steps = []
    spent_tokens = 0
    spent_seconds = 0.0
    stopped = "attempt_limit"
    for index in range(doc["max_attempts_per_arm"]):
        if spent_tokens >= doc["soft_reported_token_budget_per_arm"]:
            stopped = "token_budget_reached"
            break
        if spent_seconds >= doc["model_seconds_budget_per_arm"]:
            stopped = "time_budget_reached"
            break
        policy = "depth" if arm == "baseline" else "adaptive"
        action = select_next(policy=policy, steps=steps,
                             budget=doc["max_attempts_per_arm"], threshold=1.0)
        if action is None:
            stopped = "public_success"
            break
        parent = next((a for a in attempts if a["id"] == action["parent_attempt_id"]), None)
        remaining_seconds = max(1, int(doc["model_seconds_budget_per_arm"] - spent_seconds))
        timeout = min(doc["max_seconds_per_call"], remaining_seconds)
        request = prompt(task, broken, parent=parent,
                         new_root=action["kind"] == "new_root" and index > 0)
        model = proposer(request, timeout) if proposer else invoke_codex(request, timeout=timeout)
        spent_seconds += float(model.get("seconds") or 0)
        if isinstance(model.get("tokens"), int) and model["tokens"] >= 0:
            spent_tokens += model["tokens"]
        proposal = model.get("source")
        evaluation = (grade(task, mode="public", candidate=proposal)
                      if model.get("status") == "ok" and isinstance(proposal, str)
                      else {"status": "model_unavailable", "passed": False})
        attempt_id = "attempt-" + str(index+1)
        attempts.append({"id": attempt_id, "kind": action["kind"],
                         "parent_attempt_id": action["parent_attempt_id"],
                         "source": proposal,
                         "source_sha256": hashlib.sha256(proposal.encode("utf-8")).hexdigest()
                                           if isinstance(proposal, str) else None,
                         "model_status": model.get("status"),
                         "model_seconds": model.get("seconds"),
                         "tokens_reported": model.get("tokens"),
                         "public": evaluation})
        steps.append({"id": attempt_id, "position": index,
                      "parent_id": action["parent_attempt_id"],
                      "score": float(evaluation.get("passed") is True)})
    eligible = [x for x in attempts if x["public"]["status"] == "ok"]
    best = eligible[0] if eligible else None
    # Hidden scoring is separate and executed once per arm, never shared in prompts.
    final = (grade(task, mode="hidden", candidate=best["source"])
             if best else {"status": "no_public_solution", "passed": False})
    return {"arm": arm, "attempts": attempts, "attempts_used": len(attempts),
            "selected_attempt": best["id"] if best else None,
            "public_pass": best is not None,
            "hidden_pass": final["passed"],
            "full_success": best is not None and final["passed"],
            "final_hidden": final,
            "reported_tokens": spent_tokens,
            "token_reporting_complete": all(isinstance(x["tokens_reported"], int)
                                            for x in attempts),
            "model_seconds": round(spent_seconds,2),
            "stop_reason": stopped,
            "soft_token_budget_not_hard_enforced": True}


def execute_task(task_id, output: Path, *, approve=False):
    if approve is not True:
        raise ValueError("explicit authorization required")
    doc, protocol_hash = manifest()
    task = next((x for x in doc["tasks"] if x["id"] == task_id), None)
    if task is None:
        raise ValueError("task is not preregistered")
    if output.exists():
        raise ValueError("refusing to overwrite a recorded result")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"task_id": task_id, "protocol_sha256": protocol_hash,
              "model": doc["model"], "status": "prevalidating",
              "prevalidation": None, "arms": []}
    def checkpoint():
        stage = output.with_suffix(".partial")
        stage.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        os.replace(stage, output)
    checkpoint()
    baseline = prevalidate(task)
    report["prevalidation"] = baseline
    if not baseline["eligible"]:
        report["status"] = "prevalidation_excluded"
        checkpoint()
        return report
    report["status"] = "running"
    checkpoint()
    for arm in task["arm_order"]:
        report["arms"].append(run_arm(task, arm))
        checkpoint()
    report["status"] = "completed"
    checkpoint()
    return report
