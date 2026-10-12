"""Approval-gated, provider-neutral command readiness before scoring coding agents.

This module never reads credentials or requests model inference on its own.
A user-supplied command may incur provider charges; Nykra cannot determine
provider pricing and never claims readiness without a real output marker.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path


def probe_command(argv, *, expect="READY", timeout=30, approve=False, cwd=None):
    """Run one explicit CLI readiness invocation without shell interpolation.

    Do not return stdout/stderr content: model CLIs sometimes print secrets,
    user prompts or proprietary code into either stream.
    """
    if approve is not True:
        raise ValueError("explicit approval required to launch a provider command")
    if not isinstance(argv, (list, tuple)) or not 1 <= len(argv) <= 40:
        raise ValueError("command must contain 1-40 argv elements")
    if any(not isinstance(x, str) or not x or "\x00" in x or len(x) > 8192 for x in argv):
        raise ValueError("invalid command argument")
    if not isinstance(expect, str) or not 1 <= len(expect) <= 128 or "\n" in expect or "\r" in expect:
        raise ValueError("expect must be a nonempty single-line marker up to 128 characters")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("provider timeout must be 1-120 seconds")
    if cwd is not None:
        folder = Path(cwd).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("provider working directory does not exist")
    else:
        folder = None

    started = time.monotonic()
    stdout = b""
    stderr = b""
    exit_code = None
    state = "spawn_error"
    try:
        proc = subprocess.Popen(
            list(argv), cwd=str(folder) if folder else None,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            state = "timeout"
        else:
            exit_code = proc.returncode
            if exit_code != 0:
                state = "process_error"
            elif not stdout.strip():
                state = "empty_response"
            elif stdout.strip() == expect.encode("utf-8"):
                state = "ready"
            else:
                state = "unexpected_response"
    except OSError:
        state = "spawn_error"

    return {
        "schema": "nykra-provider-preflight-v1",
        "status": state,
        "ready": state == "ready",
        "exit_code": exit_code,
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "output_redacted": True,
        "note": ("A ready probe only confirms this specific CLI response. "
                 "It does not prove reliable longer coding generations or zero provider charges."),
    }


def probe_repeated(argv, *, runs=1, expect="READY", timeout=30,
                   approve=False, cwd=None):
    if approve is not True:
        raise ValueError("explicit approval required to launch provider readiness checks")
    if type(runs) is not int or not 1 <= runs <= 3:
        raise ValueError("repeated readiness checks require 1-3 invocations")
    attempts = [
        probe_command(argv, expect=expect, timeout=timeout, approve=True, cwd=cwd)
        for _ in range(runs)
    ]
    return {
        "schema": "nykra-provider-preflight-batch-v1",
        "invocations": len(attempts),
        "ready_count": sum(x["ready"] for x in attempts),
        "all_ready": all(x["ready"] for x in attempts),
        "attempts": attempts,
        "model_inference_authenticated": False,
        "free_model_verified": False,
        "scored_coding_attempts": 0,
        "note": ("Call only an explicitly authorized provider command. Nykra does not "
                 "read credentials, verify model pricing or launch benchmark attempts."),
    }
