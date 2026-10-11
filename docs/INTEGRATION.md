# Nykra integration contract (v2)

Nykra should be embeddable beneath different agent experiences: an MCP execution harness, a terminal agent, or an agentic IDE. **Agents do not have to call Nykra-specific tools** when their execution runtime is instrumented. Instrumentation belongs at the runtime boundary that knows which candidate, parent, workspace snapshot, and measured evaluation correspond to each attempt.

## Transport and trust

The initial bridge is an authenticated, localhost-only JSON API. Nykra automatically generates a bearer token in its per-user data directory. A trusted local bridge process can obtain this token through the `HistoryStore.token()` API or local file access with the same user's permissions. Do not expose the token to remote model prompts or send it to a remote MCP client. A tunnel-connected MCP harness should forward **sanitized event data** from its local host process, not forward Nykra's local API or token over the tunnel.

All event fields are JSON. Paths, artifact URLs, prompts, and tool transcripts should be excluded or minimized unless there is explicit opt-in and permission.

## Milestone 16: shared ancestry policy and external isolation preflight

A single pure `nykra.exploration_policy.select_next` now determines new-root or revision requests in both durable `IterativeCoding` sessions and the opt-in `nykra.repo_policy_runner` for trusted Nykra Git fixtures. It does not depend on a particular vendor model. An actual adaptive-policy Codex smoke proposal passed 26/26 independently graded cases but did not require a second attempt; no performance advantage is claimed. The external benchmark preflight (`python -m nykra benchmark preflight`) detects container runtimes and digest-pinned local image readiness without running external code. On this Windows workstation, Docker and Podman were missing and WSL did not provide a usable environment; untrusted repository execution is explicitly blocked. See [EXTERNAL_EVALUATION.md](EXTERNAL_EVALUATION.md) for prerequisites and remaining work.

## Milestone 15: real repository modules in disposable Git repair trials

Nykra now supports a host-owned, opt-in Codex patch experiment on **six genuine Nykra package modules with deliberately introduced regressions**, copied into disposable Git repositories and tested with external public/hidden cases. Both arms solved 6/6 on their first model attempt, passing 156/156 hidden checks per arm: a **ceiling effect with no observable Nykra strategy uplift**, not a general repository-fixing benchmark. Codex's Windows workspace-write mode did not permit edits, so model inference was read-only and trusted Nykra code applied strictly whitelisted function patches. This is not a verified universal Codex `AgentDriver` adapter, a hardened model sandbox, or SWE-bench. See [REPOSITORY_REPAIR_PILOT.md](REPOSITORY_REPAIR_PILOT.md).

## Milestone 14: native Codex inference and first matched bug-repair pilot

Using Rel.AI as the workstation driver, an official checksum-verified Codex CLI 0.160.0 ran authenticated GPT-6 Luna inference with bounded read-only and noninteractive settings. Two small recorded experiments compared independent restarts to source revisions on the same four synthetic Python bug-repair tasks. The original and post-hoc retry follow-up each solved **1/4** tasks per arm; the follow-up's Nykra-labelled revision prompts passed 37/128 hidden cases against 32/128 for baseline, without an additional solved task. This is **real native model execution**, but **not** native implementation of Nykra's portable `AgentDriver`, not official SWE-bench, and not a general improvement claim. The strict AST worker disallows ordinary Python constructs and needs separate hardening before more realistic repository trials. See [NATIVE_CODEX_PILOT.md](NATIVE_CODEX_PILOT.md).

## Milestone 13: real model-authored coding study and ceiling-effect finding

Eight model-authored Python solutions were executed through the working ChatGPT–Rel.AI path on new algorithmic task families. All eight scored 100% of their disjoint held-out cases on the first attempt; the correct conclusion is **no measurable added benefit in these tasks**, not a strategy win. Tests also verify that deliberately incorrect non-model controls are detected and that held-out inputs never overlap with training. A CLI replays the frozen model-authored candidates and exports task-level evidence. A headless OpenCode free-model invocation was attempted and timed out; the core does not silently fallback to a paid provider. See [REAL_CODING_STUDY.md](REAL_CODING_STUDY.md) and [machine results](evidence/v13_coding_study_results.json).

## Milestone 12: Portable driver contract and paired evidence

Nykra Core now exposes the `nykra.drivers.AgentDriver` supervised request/submit/abort protocol. The Rel.AI connected-agent adapter is the only verified implementation; other agents are discoverable as **discovery-only** and cannot be activated by Nykra yet. A new paired grid benchmark actually executes breadth/adaptive searches on equal-budget identical tasks and publishes independently verified results, but does **not** support claims of LLM coding-agent improvement. See [DRIVERS.md](DRIVERS.md), [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) and [evidence JSON](evidence/grid_paired_seed20261011.json).

## Milestone 11: Rel.AI-first turn orchestration

`nykra.relai_agent.RelaiAgent` wraps the existing evaluated iterative-coding controller for the installed ChatGPT–Rel.AI execution path. A connected model can issue repeated Rel.AI file-edit/exec tool calls in a **single authorized turn**; Nykra returns explicit parent source and training failures, chooses the requested exploration parent, and automatically completes final held-out evaluation when the score or attempt budget is reached. Candidate source is temporarily cached under the local user's Nykra home and deleted on finish/abort; it is never written to Nykra's SQLite histories. This is **not** unattended LLM inference, because the host does not provide a verified independent model-generation endpoint. See [RELAI_AUTOPILOT.md](RELAI_AUTOPILOT.md) and [AGENT_LOOP.md](../integrations/relai/AGENT_LOOP.md).

## Milestone 10: feedback-driven external-agent sessions

`nykra.iterative.IterativeCoding` stores session progress across process restarts and requests one model-authored candidate at a time under a selected breadth/depth/adaptive policy. It scores actual source through public training fixtures and returns limited failing examples; only an explicit final operation runs held-out evaluation. Candidate source code remains in the authorized agent's own files, not Nykra's databases. Rel.AI remains an execution transport; Nykra does not call or inspect the model autonomously. See [FEEDBACK_LOOP.md](FEEDBACK_LOOP.md).

## Milestone 9: supervised real AI coding tasks via Rel.AI

Nykra v0.9 introduces `nykra.relai_coding.run_proposal_trial` and its `nykra coding` CLI for actual Python coding proposals authored by ChatGPT and executed through existing Rel.AI MCP tools. The independent evaluator checks separately generated training and held-out test inputs; the prospective policy determines which candidate source functions get executed under a strict attempt budget. The historic attempt store now receives actual measured coding attempts with parent-child links; **candidate source text is not retained in Nykra SQLite**. The integration does **not** control hidden model deliberation or register new tools with Rel.AI. See [RELAI_CODING.md](RELAI_CODING.md).

## Milestone 8: executable reference search host

`nykra.agent_host.SubprocessSearchHost` executes an explicitly trusted JSON-protocol worker process to produce *new candidates at runtime* and compares breadth/depth/adaptive frontier control under prospective assignment. The packaged deterministic worker is **not a language model** and its independent grid-path evaluator supports only bounded reference mazes. The v0.8 demo creates no new tools for existing agents, does not modify the installed Rel.AI host, and cannot justify improvements in LLM performance. See [EXECUTION_HOST.md](EXECUTION_HOST.md).

## Milestone 7: prospective assignment protocol

Nykra v0.7 exposes `nykra.prospective.ProspectiveExperiment` for explicit, host-owned A/B task allocation. The trusted supervisor must execute the assigned `breadth` versus `depth` or `adaptive` policy and independently produce thresholded objective results. A separate local `prospective.sqlite3` records assignments before work begins, without mutating the active background-observer database. A closed trial with adequate arm sizes receives an advisory-only success-rate comparison and predeclared gate; **no agent policy is modified**. See [PROSPECTIVE.md](PROSPECTIVE.md) for full integration contract, privacy limits and CLI sequence.

## Milestone 6: supervised exploration intelligence

The Python module `nykra.controller` provides `SupervisedController` and `Proposal` for a trusted execution host that owns candidate generation, authorization and an independently defined evaluator. `nykra.intelligence.assess_policies` compares only evaluator-backed runs using task-disjoint training and held-out sets, returning **advisory-only**, retrospective recommendations. Historical tool-completion and IDE-save events remain unscored metadata and cannot be used as an implicit evaluator. See [INTELLIGENCE.md](INTELLIGENCE.md) for usage, assumptions and limitations. No tool schemas are added and the installed Rel.AI process remains passive.

## Milestone 3 compatibility paths

Nykra supports two distinct Rel.AI observation paths. The **read-only history observer** reads an already-installed Rel.AI host's structured SQLite events without modifying the host, selecting only tool identity, outcome, duration, event timestamp and non-content identifiers. It ignores old event timestamps by default, even when Rel.AI rewrites the database rows later. It is a development-time foreground process, not yet installed as a Windows background service.

The **direct host hook** is an optional source-level integration that subscribes to Rel.AI's existing `onToolActivity` callback. The reversible source patcher at `integrations/relai/host_integration.py` inserts that subscription in the host's actual `src/tools/callTool.js` startup path, and has been tested against a fresh Rel.AI checkout. The active desktop app remains unchanged.

For *evaluated* discovery branches, `nykra.evaluation.EvaluatedExploration` accepts a host-supplied trusted evaluator callback. It establishes a fixed evaluator ID per run and records metric scores only when that evaluator returns `EvaluatorResult`. Runtime quality evaluation, branch control and integration with a real Rel.AI planning controller remain separate future tasks; neither passive path upgrades successful tool calls into true scored discoveries.

## Passive tool-activity observations (Milestone 2)

Compatible execution runtimes can report only a completed operation's minimal outcome. This is explicitly **not** a scored discovery attempt or a reconstruction of hidden agent thinking.

`POST /v1/activity` accepts exactly `source`, `tool`, `outcome`, `duration_ms`, optional `task_id` and `event_id`. Outcomes: `succeeded`, `failed`, `cancelled`, `denied`. Identifiers use a constrained character set. Unknown JSON fields, including prompts, commands, arguments and outputs, are rejected. Idempotent duplicate events return HTTP 200; a new event returns HTTP 201. A conflicting reuse of an event ID returns an error. `GET /v1/activity` (authenticated) reads a bounded subset of recorded observations.

The Rel.AI-compatible Node adapter at `integrations/relai/bridge.mjs` subscribes once through the host's existing `onToolActivity` listener. See [REL_AI.md](REL_AI.md). It must be loaded by the host; the current installed Rel.AI application was not modified. Nykra's Python history schema upgrades older version-1 databases without dropping existing runs or attempts.

## Data model

`POST /v1/runs`:

```json
{
  "task": "Optimize query execution",
  "agent": "relai-or-local-ide",
  "evaluator_id": "repeatable-tests-v1",
  "objective": "minimize"
}
```

The response includes a generated `id`. A run represents one task under a fixed evaluator and objective. Different evaluator versions should be treated as different, non-comparable runs unless a caller establishes calibrated comparability.

`POST /v1/attempts`:

```json
{
  "run_id": "RUN_ID",
  "attempt_id": "candidate-2",
  "parent_id": "candidate-1",
  "status": "ok",
  "score": 125.4,
  "cost_units": 1.0,
  "elapsed_ms": 1100,
  "snapshot_ref": "git:abcdef123456",
  "metadata": {"evaluator": "repeatable-tests-v1"}
}
```

`parent_id` may be null for a new root branch. A parent must refer to an already-recorded attempt in the same run. Nykra stores `snapshot_ref` as a reference only; it does not checkout, modify, or retain worktrees. Invalid or failed attempts may have `score: null`. `cost_units` is caller-defined and only comparable if produced with consistent units.

`POST /v1/replay`:

```json
{
  "run_id": "RUN_ID",
  "policy": "adaptive",
  "budget": 10,
  "workers": 2,
  "cost_weight": 0,
  "parallelism_weight": 0
}
```

Supported policies: `breadth`, `depth`, `adaptive`. Return includes revealed IDs, best valid score, attainment curve, recorded/replayed attempt counts, measured cost and round count. A missing outcome cannot be replayed as if it existed.

## Rel.AI / remote MCP integration design

The host-side runtime—not the remote language model—would emit a `run` event when a controlled exploration begins and an `attempt` event **after** its evaluator finishes. The bridge should reference an immutable workspace snapshot or Git commit when it exists, and use the real parent from its task graph. A sequence of ordinary tool calls must **not** be presented as a discovery tree when no branching evidence exists.

A future bridge may attach a recommendation to existing task-bootstrap context or intercept supervised execution decisions. The Milestone 2 bridge consumes the existing completion-event stream but does not modify Rel.AI, change its MCP tools, or interfere with any live task. Live deployment within a Rel.AI host build is still pending.

## IDE integration design

Detect only supported documented extension APIs/hooks with user permission. Prefer structured test/benchmark events over speculative interpretations of file changes. Apply best-effort passive capture for agents without control hooks. Never claim active recursive improvement in passive mode.

## Non-goals of v0.2

No autonomous agent control, no fine-tuning, no self-modifying code, no replay-based prediction of counterfactual code changes, no background surveillance, no uncontrolled execution of previous failures, no automatic installation into all IDEs. The future zero-configuration end-user installer is a product milestone, not a property of the source checkout.
