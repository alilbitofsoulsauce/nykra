"""v0.24 local content-addressed PUBLIC Docker evaluation receipts.

Opt-in only. A successful cache hit reuses verified actual public Git/Docker
work from an independent session, not a model answer. A hit must match the
source, upstream Git source and public test, evaluator implementation, pinned
Docker base image ID, task protocol and patch bytes. Hidden grades are never
stored or restored. Cache is trusted local-user state, not an adversary-proof
cryptographic ledger (someone able to edit the entire host can forge it).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from .v20_grader import ROOT, _git
from .v21_grader import IMAGE_TAG, manifest

CACHE_ROOT = ROOT / "experiments" / "public-receipts-v24"
_OWNER = "nykra-public-receipts-local-host-v24"
_HEX = re.compile(r"^[0-9a-f]{64}$")


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _encode(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _trusted_root():
    if CACHE_ROOT.is_symlink():
        raise ValueError("public cache directory is a symlink")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    marker = CACHE_ROOT / "OWNER"
    if marker.is_symlink():
        raise ValueError("untrusted public cache owner marker")
    if not marker.exists():
        try:
            with marker.open("x", encoding="ascii") as f:
                f.write(_OWNER)
        except FileExistsError:
            pass
    if marker.read_text(encoding="ascii") != _OWNER:
        raise ValueError("unexpected local public cache owner")
    return CACHE_ROOT


def context(task: dict, source: str, patch_recipe) -> tuple[str, dict, tuple]:
    """Compute a key containing every relevant PUBLIC source/evaluator input."""
    config, protocol_sha = manifest()
    if task["id"] not in {t["id"] for t in config["tasks"]}:
        raise ValueError("task not authorized by evaluator")
    patch, before, after = patch_recipe(task, source)
    parent = Path(__file__).parent
    dependencies = [
        "v21_grader.py", "v20_grader.py", "repair_feedback.py",
        "repository_repair_trial.py", "agent_workflow.py",
    ]
    sha_code = {name: _sha((parent / name).read_bytes()) for name in dependencies}
    file_test = _git(task, task["fixed_commit"], task["test_file"])
    payload = {
        "schema": "nykra-public-cache-key-v24",
        "task_id": task["id"],
        "protocol_sha256": protocol_sha,
        "source_sha256": _sha(source.encode("utf-8")),
        "patch_sha256": _sha(patch.encode("utf-8")),
        "git_original_sha256": before,
        "git_after_sha256": after,
        "upstream_buggy_commit": task["buggy_commit"],
        "upstream_fixed_commit": task["fixed_commit"],
        "public_test_source_sha256": _sha(file_test),
        "public_test_selector": task["public_test"],
        "image_id": config["docker_image_id"],
        "evaluator_code_sha256": sha_code,
    }
    return _sha(_encode(payload)), payload, (patch, before, after)


def _image_available(expected_id: str):
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE_TAG],
            capture_output=True, timeout=16)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.decode("ascii", "replace").strip() == expected_id


def _read_receipt(path: Path, digest: str, payload: dict, patch: str):
    if not _HEX.fullmatch(digest) or path.is_symlink():
        raise ValueError("untrusted local cache file")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 80000:
        raise ValueError("invalid local cache file")
    try:
        entry = json.loads(path.read_bytes())
    except (ValueError, UnicodeError) as err:
        raise ValueError("corrupt local public cache receipt") from err
    checksum = entry.pop("receipt_sha256", None)
    if (not isinstance(checksum, str)
            or checksum != _sha(_encode(entry))
            or entry.get("schema") != "nykra-public-receipt-v24"
            or entry.get("cache_key") != digest
            or entry.get("inputs") != payload
            or entry.get("patch") != patch):
        raise ValueError("local cache receipt provenance mismatch")
    public = entry.get("public")
    if (not isinstance(public, dict)
            or public.get("status") not in ("ok", "test_failed")
            or type(public.get("passed")) is not bool
            or public["passed"] != (public["status"] == "ok")
            or "hidden" in entry):
        raise ValueError("invalid cached public grader verdict")
    return public


def _store_receipt(path: Path, digest: str, inputs: dict, patch: str, public: dict):
    if public.get("status") not in ("ok", "test_failed"):
        return False
    value = {"schema": "nykra-public-receipt-v24", "cache_key": digest,
             "inputs": inputs, "patch": patch, "public": public}
    value["receipt_sha256"] = _sha(_encode(value))
    if path.is_symlink():
        raise ValueError("refuse symlinked cache entry")
    with path.open("xb") as file:
        blob = json.dumps(value, indent=2, ensure_ascii=True).encode("utf-8") + b"\n"
        if len(blob) > 80000:
            raise ValueError("cache receipt exceeds limit")
        file.write(blob)
        file.flush()
        os.fsync(file.fileno())
    return True


def evaluate(task, source: str, *, patch_recipe, materialize, grader):
    """One local exact input: either real Git+Docker or a checked public receipt.

    An OS advisory lock serializes cache access for identical inputs. Where
    a concurrent host still holds the lock, wait a finite amount and fail
    closed rather than run unverified duplicate code or forge a hit.
    """
    from .workstation import _single_instance
    root = _trusted_root()
    key, inputs, recipe = context(task, source, patch_recipe)
    path = root / (key + ".json")
    lock = root / (key + ".lock")
    if lock.is_symlink():
        raise ValueError("untrusted cache lock")
    # Bounded waiting protects against duplicate cold evaluations by
    # simultaneous independent agent sessions.
    deadline = time.monotonic() + 130
    while True:
        try:
            with _single_instance(lock):
                # Do not claim that tests passed when the pinned runtime is
                # missing or its image ID has changed.
                if not _image_available(inputs["image_id"]):
                    raise ValueError("pinned public evaluator Docker image is unavailable")
                hit = _read_receipt(path, key, inputs, recipe[0])
                if hit is not None:
                    return {
                        "patch": recipe[0], "before": recipe[1],
                        "after": recipe[2], "public": hit,
                        "hit": True, "cache_key": key,
                        "git_apply_calls": 0, "public_docker_calls": 0,
                    }
                patch, before, after = materialize(task, source)
                if (patch, before, after) != recipe:
                    raise ValueError("Git patch does not match exact cache key")
                public = grader(task, mode="public", candidate=source)
                # Failed/invalid infrastructure is not cached.
                if public["status"] in ("ok", "test_failed"):
                    _store_receipt(path, key, inputs, patch, public)
                return {
                    "patch": patch, "before": before, "after": after,
                    "public": public, "hit": False, "cache_key": key,
                    "git_apply_calls": 1, "public_docker_calls": 1,
                }
        except Exception as err:
            # Only the busy advisory lock should be retried, never an
            # evaluator, provenance, disk or validation error.
            if type(err).__name__ != "NykraError" or "already running" not in str(err):
                raise
            if time.monotonic() > deadline:
                raise ValueError("timed out waiting for exact-input cache lock") from err
            time.sleep(0.2)
