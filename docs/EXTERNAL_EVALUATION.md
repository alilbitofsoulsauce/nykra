# Nykra v0.16 — Portable policy engine and external evaluation readiness

## Achieved engineering milestone

Nykra now exposes one pure, deterministic scored-attempt decision function in nykra/exploration_policy.py. It is shared by the older durable IterativeCoding sessions and the newer trusted-repository Codex adapter in nykra/repo_policy_runner.py. It accepts a policy, prespecified attempt budget, passing threshold, and actual evaluated attempt ancestry. It can request an independent root or select an existing parent for revision. It never invokes a model or changes the evaluator, and it verifies ordered parent-child history and finite scores.

The repository exploration runner is **restricted to existing, explicitly enumerated, trusted Nykra regression fixtures**. It sends only the faulty function and public feedback to Codex, retains scored candidate ancestry in the experiment result, and runs the private evaluator only after candidate selection. It is not the official native Codex AgentDriver adapter; it uses the previously verified authorized Codex CLI as a replaceable inference engine.

## Environment and security finding

At the start of this milestone on October 11, 2026, the workstation was Windows 11. Docker and Podman CLIs were absent; wsl.exe was present but the WSL status command returned exit code 50. This does not provide an available isolated Linux evaluator. Detection of WSL, a running Docker daemon, or a pinned image by itself does not prove adversarial security.

The new read-only preflight command is:

    python -m nykra benchmark preflight

Optionally provide the name and SHA-256 digest of a locally available image:

    python -m nykra benchmark preflight --image docker.io/example/benchmark@sha256:<64_hex_digits>

The preflight never pulls an image, runs arbitrary code, enables OS features, or grants model permissions. It reports installed container backends, service readiness, requested-image digest locking, and required isolation controls. Critically it returns external_benchmark_ready=false and execution_authorized=false until a separate backend has run and attested a constrained sandbox smoke test. Its guard rejects unverified external execution even when callers claim a successful smoke test.

## October 11, 2026 — post-reboot Docker smoke verified

After Docker Desktop installation and reboot, `docker info` reported **Engine 29.8.2**, Linux containers and `overlayfs`; WSL reported version 2 with `docker-desktop` as the default distribution. C: had only **3,012,702,208 bytes free** before downloading the small smoke image. Official SWE-bench's recommended disk resources are not available on this laptop.

A pinned official BusyBox image was downloaded and then used by the built-in fixed-command smoke runner:

```powershell
python -m nykra benchmark smoke --image docker.io/library/busybox@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e --approve
```

The [machine-readable smoke result](evidence/docker_smoke_2026-10-11.json) records a real successful container run using no network, a read-only root, UID 65534, dropped capabilities, no-new-privileges, bounded CPU/memory/process/time limits, a disposable tmpfs workdir, and no host-directory mounts. The fixed script independently checked nonroot execution, writable temporary storage, denied writes to `/etc`, and a fresh output nonce. Neither benchmark repositories nor external code were executed.

**Scope limitation:** This is a constrained benign smoke, not a validated hostile-code sandbox, full per-task evaluator or independent coding benchmark. `execution_authorized=false` and `external_benchmark_ready=false` remain intentional. A separate per-task container verifier, image/task manifests, adversarial isolation checks, resource budgets and independently graded real issue repairs are still required.

## Official external benchmark requirements

SWE-bench uses container-based evaluations. Its official setup guidance recommends Docker, ample disk space (at least 120 GB free), and at least 16 GB RAM; resource consumption varies by dataset and concurrency. The currently available SWE-bench Pro V2 benchmark provides public container images, task verifiers, and independently graded patches. None of those external benchmark tasks was executed by Nykra during this milestone.

References:

- https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/docker_setup.md
- https://github.com/scaleapi/SWE-bench_Pro-os/blob/main/v2/README.md
- https://learn.microsoft.com/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install

## Required work before external issue-repair testing

1. Provision a dedicated Linux VM or Docker/Podman host with validated resource limits, network-disabled execution, nonroot UID, a read-only base image, no privileged mounts, and a fresh worktree per task.
2. Implement a container-backed verifier that runs a harmless offline smoke test under the same policy and emits a trustworthy, versioned attestation. Never accept a caller-supplied success boolean as proof of isolation.
3. Select previously unseen external issue-fixing tasks and freeze the manifests, grading definitions, tool access, model configuration, cost/token/time budgets, and randomized task assignment before model generation.
4. Use Nykra's actual shared policy engine for parent/branch selection in the guided arm, not merely a string prompt labeled Nykra. The other arm should have equal opportunities and budgets.
5. Evaluate candidate patches in fresh independent containers and publish task-level success, regressions, timeouts, token usage, costs and statistical uncertainty. Do not treat hundreds of hidden test cases as independent tasks.

## Evidence limitations

Earlier benchmark results remain immutable. V0.15 yielded 6/6 full-task successes in both matched arms, with one model attempt each, so the Nykra revision strategy was never invoked and no uplift was observed. This v0.16 refactor proves shared policy mechanics and isolation-gating behavior, **not a general coding-agent improvement**, secure Windows host evaluation, policy learning, model self-improvement, or an official SWE-bench score.

Direct source and local assertions:

    python -m unittest discover -s tests -p test_exploration_policy.py -v
    python -m unittest discover -s tests -p test_repo_policy_runner.py -v
    python -m unittest discover -s tests -p test_external_isolation.py -v
    python -m nykra doctor
