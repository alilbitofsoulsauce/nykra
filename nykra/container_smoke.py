"""Constrained, fixed-command Docker smoke test.

This verifies that a selected local digest-pinned image runs under restrictive
Docker settings. It never evaluates externally supplied repository code and
does not authorize external execution. Docker is not a security boundary for
arbitrary hostile code merely because these flags are present.
"""
from __future__ import annotations

import secrets
import shutil
import subprocess
from typing import Any

from .external_isolation import isolation_preflight
from .store import NykraError

# Fixed benign script; no input, repository content or caller-provided command
# is interpolated into the shell source.
_SMOKE_SCRIPT = (
    'test "$(id -u)" = 65534 && '
    'test -w /work && '
    'touch /work/nykra-test && rm /work/nykra-test && '
    'if touch /etc/nykra-test >/dev/null 2>&1; then exit 13; fi; '
    'printf "%s\\n" "$NYKRA_SMOKE_NONCE"'
)


def run_container_smoke(*, image: str, approval: bool = False) -> dict[str, Any]:
    """Run only the built-in offline smoke script, never benchmark code."""
    if approval is not True:
        raise NykraError("container smoke requires explicit --approve")
    preflight = isolation_preflight(image=image)
    if not preflight["ready_for_container_smoke_test"]:
        raise NykraError("container smoke requires a locally cached digest-pinned image and a running Docker daemon")
    if not preflight["container_runtimes"]["docker"]["responding"]:
        raise NykraError("container smoke currently supports Docker only")
    binary = shutil.which("docker")
    if not binary:
        raise NykraError("Docker executable not found")

    nonce = secrets.token_hex(16)
    command = [
        binary, "run", "--rm", "--pull", "never",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64",
        "--memory", "128m", "--memory-swap", "128m",
        "--cpus", "1",
        "--user", "65534:65534",
        "--tmpfs", "/work:rw,nosuid,nodev,noexec,size=16m,mode=1777",
        "--workdir", "/work",
        "--env", "NYKRA_SMOKE_NONCE=" + nonce,
        "--entrypoint", "/bin/sh",
        image, "-ec", _SMOKE_SCRIPT,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, errors="replace",
            timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NykraError("restricted Docker smoke could not complete") from exc
    if completed.returncode != 0 or completed.stdout.strip() != nonce:
        # Do not echo stderr; Docker/image failures could expose host details.
        raise NykraError("restricted Docker smoke failed its exit/output checks")
    return {
        "protocol": "nykra-fixed-container-smoke-v1",
        "image": image,
        "smoke_passed": True,
        "checks": [
            "digest_pinned_locally_available_image", "no_network",
            "read_only_root", "nonroot_uid_65534", "drop_all_capabilities",
            "no_new_privileges", "bounded_cpu_memory_pids_and_wall_time",
            "ephemeral_tmpfs_workdir", "no_host_mounts",
            "writable_workdir_verified", "root_write_denied_verified",
            "fresh_nonce_output_verified",
        ],
        "untrusted_repository_code_executed": False,
        "execution_authorized": False,
        "external_benchmark_ready": False,
        "limitations": (
            "A constrained fixed-command smoke check is not sufficient to "
            "certify hostile-code isolation or authorize external benchmarks."
        ),
    }
