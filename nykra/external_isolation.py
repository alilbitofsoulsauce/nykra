"""Fail-closed preflight for externally supplied repository evaluations.

External projects may execute setup scripts and arbitrary test code.
Do not run them using Nykra's Windows host Python evaluator. Checking a
Docker/Podman executable or WSL presence is not security isolation.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from .store import NykraError

IMAGE_DIGEST = re.compile(r"\A[a-zA-Z0-9._/-]+@sha256:[0-9a-f]{64}\Z")
BACKENDS = ("docker", "podman")
_HARDENING = {
    "network": "none",
    "filesystem": "read-only-rootfs-with-dedicated-writable-workdir",
    "user": "nonroot",
    "capabilities": "drop-all",
    "privileges": "no-new-privileges",
    "resources": "explicit memory/cpu/pid/wall-time limits",
    "project": "independent disposable copy; no credentials or host-state mounts",
}


def _status(command: str, argv: list[str], *, timeout: int = 7) -> dict[str, Any]:
    binary = shutil.which(command)
    if not binary:
        return {"detected": False, "responding": False, "reason": "not_installed"}
    try:
        proc = subprocess.run(
            [binary, *argv], capture_output=True, text=True,
            errors="replace", timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"detected": True, "responding": False, "reason": "timed_out"}
    except OSError:
        return {"detected": True, "responding": False, "reason": "not_launchable"}
    return {
        "detected": True,
        "responding": proc.returncode == 0,
        "reason": "ok" if proc.returncode == 0 else "service_not_ready",
    }


def isolation_preflight(*, image: str | None = None) -> dict:
    """Read-only check; intentionally never pulls images, starts VMs or runs code."""
    containers = {
        backend: _status(backend, ["info", "--format", "{{.ServerVersion}}"])
        for backend in BACKENDS
    }
    # WSL presence alone is never treated as a verified sandbox.
    wsl = _status("wsl", ["--list", "--quiet"], timeout=6)
    image_valid = bool(image and IMAGE_DIGEST.fullmatch(image))
    viable = [name for name in BACKENDS if containers[name]["responding"]]
    image_local = False
    if image_valid and viable:
        backend = viable[0]
        result = _status(backend, ["image", "inspect", "--format", "{{.Id}}", image])
        image_local = result["responding"]
    ready_for_smoke_test = bool(viable and image_valid and image_local)
    # We do NOT claim full execution readiness until an isolated smoke test
    # runs successfully with resource and mount constraints. This tool does not
    # perform such a test.
    return {
        "purpose": "untrusted_external_repository_execution",
        "container_runtimes": containers,
        "wsl": {**wsl, "counts_as_verified_isolation": False},
        "requested_image": image,
        "image_digest_locked": image_valid,
        "image_available_locally": image_local,
        "ready_for_container_smoke_test": ready_for_smoke_test,
        "execution_authorized": False,
        "external_benchmark_ready": False,
        "required_controls": _HARDENING,
        "blocked_reason": (
            "A verified, resource-limited offline container runtime is required "
            "before external repository code can execute. Detection alone does "
            "not establish safe container isolation."
        ),
    }


def require_verified_external_isolation(preflight: dict, *, smoke_attestation: bool) -> None:
    """Conservative gate; explicitly rejects unchecked external tasks.

    An actual execution backend must supply a fresh verified smoke attestation
    after enforcing resource, mount and network policy. This function alone
    cannot attest that those controls were actually applied.
    """
    # A plain boolean supplied by a caller cannot attest that resource,
    # mount, privilege and network restrictions were actually enforced.
    # Until an isolated executor performs and records its own smoke test,
    # external execution remains unavailable regardless of claimed status.
    raise NykraError(
        "external repository evaluation blocked: no verified isolated executor installed"
    )
