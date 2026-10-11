"""Small isolated pilot for real historical BugsInPy youtube-dl fixes.

Operator-supplied trusted task manifests refer to real upstream buggy commits.
Never run repo code on the Windows host. The grader uses a pinned Python Docker
image, no network, no runtime host mounts, read-only root, nonroot UID,
CPU/memory/PID/time budgets, and fresh disposable build contexts.

This is NOT the official BugsInPy harness, an adversarially certified sandbox,
or an official SWE-bench evaluation. The associated test suite has access to
the real historic regression tests, never the model inference prompt.
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

from .repository_repair_trial import extract_function, replace_function, invoke_codex
from .exploration_policy import select_next

BASE_IMAGE = "docker.io/library/python@sha256:e191a71397fd61fbddb6712cd43ef9a2c17df0b5e7ba67607128554cd6bff267"
DATASET = Path(__file__).resolve().parents[1] / "experiments/bugsinpy-source"
SOURCE = Path(__file__).resolve().parents[1] / "experiments/bench-source/youtube-dl"
PROTOCOL = Path(__file__).resolve().parents[1] / "docs/evidence/v17_external_pilot_protocol.json"
SOURCE_FILE = "youtube_dl/utils.py"
TEST_FILE = "test/test_utils.py"
MAX_ARCHIVE_BYTES = 18_000_000
MAX_PATCH_BYTES = 16000


def checked_run(argv, *, cwd=None, timeout=30, stdin=None):
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, input=stdin,
                          timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError("controlled host operation failed: " + argv[0])
    return proc.stdout


def read_manifest():
    raw = PROTOCOL.read_bytes()
    data = json.loads(raw)
    if data["id"] != "nykra-real-bugsinpy-pilot-v1":
        raise ValueError("invalid frozen task manifest")
    if data["docker_image"] != BASE_IMAGE:
        raise ValueError("container image mismatch")
    return data, hashlib.sha256(raw).hexdigest()


def git_bytes(ref: str, filename: str):
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("commit must be 40 hex bytes")
    if filename not in (SOURCE_FILE, TEST_FILE):
        raise ValueError("unregistered file")
    return checked_run(["git", "show", ref + ":" + filename], cwd=SOURCE, timeout=30)


def extract_commit(ref: str, dest: Path):
    archive = checked_run(["git", "archive", "--format=tar", ref], cwd=SOURCE, timeout=90)
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("external source exceeds frozen 18MB extraction limit")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as files:
        total = 0
        for member in files:
            name = member.name.replace("\\", "/")
            path = Path(name)
            if (path.is_absolute() or ".." in path.parts or
                    not (member.isfile() or member.isdir())):
                raise ValueError("unsafe or unsupported source archive member")
            target = dest / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                total += member.size
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("external source exceeds source limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with files.extractfile(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    # Ensure unknown upstream Docker instructions are never executed.
    (dest / ".dockerignore").write_text("**/.git\n**/.env\n**/__pycache__\n", encoding="utf-8")
    (dest / "Dockerfile.nykra").write_text(
        "FROM " + BASE_IMAGE + "\n"
        "COPY . /repo/\n"
        "WORKDIR /repo\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/repo HOME=/tmp\n"
        "USER 65534:65534\n", encoding="utf-8",
    )


def prepare(task: dict, dest: Path, *, replacement: str | None = None):
    extract_commit(task["buggy_commit"], dest)
    # Independent regression tests from official fixed commit, not source fix.
    (dest / TEST_FILE).write_bytes(git_bytes(task["fixed_commit"], TEST_FILE))
    if replacement is not None:
        module = dest / SOURCE_FILE
        original = module.read_text(encoding="utf-8")
        module.write_text(replace_function(original, task["function"], replacement),
                          encoding="utf-8")


def grader(task: dict, replacement: str | None = None) -> dict:
    """Grade one candidate in a fresh image; do not leak test stdout to model."""
    started = time.monotonic()
    if replacement is not None and len(replacement.encode("utf-8")) > MAX_PATCH_BYTES:
        return {"status": "invalid_patch", "passed": False, "elapsed": 0}
    tag = "nykra-pilot-" + uuid.uuid4().hex[:15]
    image_id = None
    with tempfile.TemporaryDirectory(prefix="nykra-real-eval-") as tmp:
        root = Path(tmp)
        try:
            prepare(task, root, replacement=replacement)
            build = subprocess.run(
                ["docker", "build", "--network", "none", "--pull=false",
                 "-f", str(root / "Dockerfile.nykra"), "-t", tag, str(root)],
                capture_output=True, timeout=90, check=False,
            )
            if build.returncode:
                return {"status": "build_failed", "passed": False,
                        "elapsed": round(time.monotonic()-started, 2)}
            image_id = checked_run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
                timeout=10).decode().strip()
            argv = [
                "docker", "run", "--rm", "--pull", "never",
                "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "64", "--memory", "384m", "--memory-swap", "384m",
                "--cpus", "1", "--user", "65534:65534",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m",
                "--workdir", "/repo", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONPATH=/repo", "--env", "HOME=/tmp",
                "--entrypoint", "python", image_id,
                "-B", "-m", "unittest", "-q", task["regression_test"],
            ]
            try:
                done = subprocess.run(argv, capture_output=True, timeout=40,
                                      check=False)
                return {
                    "status": "ok" if done.returncode == 0 else "test_failed",
                    "passed": done.returncode == 0,
                    "exit_code": done.returncode,
                    "elapsed": round(time.monotonic() - started, 2),
                    "image_id": image_id,
                    "stderr_sha256": hashlib.sha256(done.stderr).hexdigest(),
                    "stderr_bytes": len(done.stderr),
                }
            except subprocess.TimeoutExpired:
                return {"status": "timeout", "passed": False,
                        "elapsed": round(time.monotonic() - started, 2)}
        except (OSError, RuntimeError, ValueError, UnicodeError, SyntaxError,
                subprocess.TimeoutExpired) as exc:
            return {"status": "setup_error", "error_type": type(exc).__name__,
                    "passed": False, "elapsed": round(time.monotonic()-started, 2)}
        finally:
            if image_id:
                subprocess.run(["docker", "image", "rm", "-f", tag],
                               capture_output=True, timeout=20, check=False)


def prevalidate(task: dict) -> dict:
    good = git_bytes(task["fixed_commit"], SOURCE_FILE).decode("utf-8")
    golden_source = extract_function(good, task["function"])
    # Never send the gold source or its contents to an agent.
    broken = grader(task)
    fixed = grader(task, replacement=golden_source)
    return {"buggy": broken, "reference_fix": fixed,
            "eligible": (broken["status"] == "test_failed"
                         and fixed["status"] == "ok")}


def task_prompt(task: dict, broken: str, *, parent=None, root_again=False):
    prompt = (
        "Repair one real historical bug in the youtube-dl Python project. "
        'Return JSON with ONLY the key "source" containing exactly one '
        "full top-level Python function definition. Keep its name and signature; "
        "do not add imports outside the function. "
        "The original module contains its existing imports and helpers. "
        "Only the named function will be replaced. No tools or external sources "
        "are needed or permitted; use the provided issue and code.\n"
        "ISSUE: " + task["issue"] +
        "\nTARGET FUNCTION: " + task["function"] +
        "\nBUGGY SOURCE:\n" + broken +
        "\nPUBLIC CHECK: " + task["regression_test"] + ".\n"
    )
    if parent is None:
        prompt += "\nGenerate an independent corrected solution."
    else:
        prompt += ("\nPREVIOUS SOURCE:\n" + str(parent.get("source")) +
                   "\nPREVIOUS PUBLIC RESULT:\n" +
                   json.dumps(parent["public"]) +
                   "\nRepair from the selected parent source based on feedback.")
    if root_again:
        prompt += "\nEXPLORATION: Start a new independent root. Discard previous approach."
    return prompt


def run_arm(task: dict, *, arm: str, attempts_budget: int, timeout: int) -> dict:
    assert arm in ("baseline", "nykra")
    broken_text = git_bytes(task["buggy_commit"], SOURCE_FILE).decode("utf-8")
    broken = extract_function(broken_text, task["function"])
    state = []
    attempts = []
    total_seconds = 0.0
    for index in range(attempts_budget):
        # Baseline always follows depth, Nykra executes the actual shared
        # adaptive policy, including independently rooted retries on stagnation.
        policy = "depth" if arm == "baseline" else "adaptive"
        action = select_next(policy=policy, steps=state,
                             budget=attempts_budget, threshold=1.0)
        if action is None:
            break
        parent_id = action["parent_attempt_id"]
        parent = next((x for x in attempts if x["id"] == parent_id), None)
        prompt = task_prompt(task, broken, parent=parent,
                             root_again=action["kind"] == "new_root" and index>0)
        model = invoke_codex(prompt, timeout=timeout)
        total_seconds += model.get("seconds") or 0.0
        candidate = model.get("source")
        if model.get("status") == "ok" and isinstance(candidate, str):
            public = grader(task, replacement=candidate)
        else:
            public = {"status": "model_unavailable", "passed": False}
        attempt = {
            "id": "attempt-" + str(index+1),
            "kind": action["kind"], "parent_attempt_id": parent_id,
            "source": candidate,
            "source_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                             if isinstance(candidate, str) else None,
            "model_status": model.get("status"),
            "model_seconds": model.get("seconds"),
            "reported_tokens": model.get("tokens"),
            "public": public,
        }
        attempts.append(attempt)
        state.append({"id": attempt["id"], "position": index,
                      "score": float(public["passed"]),
                      "parent_id": parent_id})
    candidates = [x for x in attempts if x["public"]["status"] == "ok"]
    best = candidates[0] if candidates else None
    # The original registered regression test is used as a diagnostic after
    # every attempt. This small pilot has NO independent hidden test.
    return {
        "arm": arm, "status": "completed", "attempts": attempts,
        "attempts_used": len(attempts),
        "selected_attempt": best["id"] if best else None,
        "regression_test_passed": bool(best),
        "total_model_seconds": round(total_seconds, 2),
        "tokens_reported": sum(x["reported_tokens"] or 0 for x in attempts),
        "tokens_complete": all(x["reported_tokens"] is not None for x in attempts),
        "hidden_evaluation_independent": False,
    }


def run_task(task_id: str, outfile: Path, *, approve: bool = False) -> dict:
    if approve is not True:
        raise ValueError("model execution requires explicit approval")
    manifest, digest = read_manifest()
    task = next((x for x in manifest["tasks"] if x["id"] == task_id), None)
    if task is None:
        raise ValueError("task not registered in frozen protocol")
    if outfile.exists():
        raise ValueError("will not overwrite prior task evidence")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    report = {"id":task_id, "protocol_sha256":digest, "source_commit":task["buggy_commit"],
              "status":"prevalidating", "model":manifest["model"],
              "arms":[], "prevalidation":None}
    def checkpoint():
        out = outfile.with_suffix(".partial")
        out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        os.replace(out,outfile)
    checkpoint()
    checks = prevalidate(task)
    report["prevalidation"] = checks
    if not checks["eligible"]:
        report["status"] = "infrastructure_excluded"
        checkpoint()
        return report
    report["status"] = "running"
    checkpoint()
    for arm in task["arm_order"]:
        report["arms"].append(run_arm(task, arm=arm,
                attempts_budget=manifest["attempts_per_arm"],
                timeout=manifest["seconds_per_model_call"]))
        checkpoint()
    report["status"] = "completed"
    checkpoint()
    return report
