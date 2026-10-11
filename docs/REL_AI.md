# Rel.AI transparent event integration

This folder contains **Nykra's side of the adapter**, which was designed against the public Rel.AI source's existing `onToolActivity(listener)` hook in `src/toolActivity.js` (inspected October 11, 2026).

**Status:** Tested against an in-process harness-style activity emitter and an actual localhost Nykra server. **Not installed into the running Rel.AI desktop app.** Rel.AI must opt to load this module in its own host process (for example, when bundling Nykra support in a release); installing the standalone Nykra core cannot attach itself invisibly to an arbitrary running process.

## Milestone 11: agent-driven coding loop (separate from passive observation)

Nykra v0.11 adds `python -m nykra relai-agent ...` for an agent connected via existing Rel.AI MCP tools. Within one authorized agent turn, the model can submit individual source candidates, receive training failures and parent code, and let Nykra automatically finalize the best tested candidate on held-out fixtures. **Rel.AI has no verified locally callable model-inference endpoint**, so this is not unattended background model generation. It uses a bounded, temporary local source cache, cleared on finish/abort; details and commands are in [RELAI_AUTOPILOT.md](RELAI_AUTOPILOT.md).

## Milestone 3: observe a running Rel.AI installation without patching it

Nykra v0.3 adds a **read-only compatibility reader** for the Rel.AI SQLite state store. The installed host does not need to be restarted or modified. In a Nykra checkout, run:

```sh
python -m nykra watch-relai
```

The reader discovers `~/.rel-ai-mcp/durable-state.sqlite` (or the `REL_AI_MCP_STATE_DIR` override), opens it in SQLite read-only mode, checks that the supported task-history event projection exists, and polls for newly finished events. Its SQL projects **only** tool names, outcomes, durations, event time and stable identifiers; it does not retrieve raw command or prompt bodies. Historical task rows are sometimes rewritten under new database timestamps, so the watcher additionally enforces the original event timestamp to avoid accidentally backfilling earlier activity.

By default, **no prior history is imported**. For an explicitly requested diagnostic import of recent history, use `python -m nykra watch-relai --once --backfill`. This can import historical activity into Nykra and should not be run when historic capture is unwanted.

`watch-relai` is a foreground developer command, not a background service installer. Stop with Ctrl+C. It writes only to Nykra's local database, not to Rel.AI's source database; no host API key, MCP tool, restart or IDE-specific configuration is needed. Support depends on Rel.AI preserving its SQLite task-history event schema. This is **passive** observation, not active agent optimization.

The adapter was exercised against the installed Rel.AI state store on October 11, 2026. Real new activity reached Nykra; a temporary test-specific Nykra database was used and the observer was stopped after verification.

## Reversible direct host hook for source builds

To integrate the lower-latency event stream into a **supported Rel.AI source checkout** rather than a running installed binary:

```sh
python integrations/relai/host_integration.py --host PATH_TO_RELAI_SOURCE
python integrations/relai/host_integration.py --host PATH_TO_RELAI_SOURCE --apply
python integrations/relai/host_integration.py --host PATH_TO_RELAI_SOURCE --remove
```

The hook installs a copy of `bridge.mjs` inside `src/tools/` and attaches beside Rel.AI's existing `bindTaskHistoryActivityPersistence(onToolActivity, readConfig)` subscription. The installer is idempotent, records content digests, preserves line endings, refuses incompatible hosts, and supports byte-for-byte rollback provided its managed source has not subsequently been modified. It never edits a running desktop application, changes MCP schemas, or rewrites agent prompts. **This patch has been tested against a fresh copy of Rel.AI's public source and then reversed; it has not been deployed into the installed desktop app.**

The patched host requires Nykra's localhost service to run in order to deliver events. When it is absent, the bridge drops observations without blocking the agent. A future packaged release will manage service startup and permissions automatically.

## Evaluator-backed exploration

Ordinary completion events and SQLite history are **not discovery-tree evidence**. For genuine quality measurements, a trusted supervisor can use `nykra.evaluation.EvaluatedExploration` with a callable evaluator returning `EvaluatorResult(score, cost_units, snapshot_ref)`. Its run fixes the evaluator identity; it records evaluated candidate parentage and rejects non-finite scores, while sanitizing evaluator exceptions. It does not infer a candidate's quality from tool success and does not make the current Rel.AI host automatically generate controlled candidate branches.

## What changes for an agent?

Nothing. The bridge subscribes **once in the execution host**. Existing ChatGPT-to-Rel.AI MCP tool names, schemas, approval boundaries, replies, and prompts remain unchanged. It captures completion events from agents connected through that host rather than registering a new MCP server for each agent.

In a host build that bundles the Nykra bridge, the integration is:

~~~js
import { onToolActivity } from './toolActivity.js';
import { attachRelaiBridge } from './integrations/nykra/bridge.mjs';

// Call once during host startup; no per-agent configuration.
const nykra = attachRelaiBridge(onToolActivity);

// On graceful shutdown (if available):
await nykra.close();
~~~

The relative bridge import is illustrative of a host-bundled copy of this file. The host distributor must package it and decide how the local Nykra daemon is started or detected. Nykra's core Python code is not imported by the Rel.AI process.

## Local prerequisites during development

Start the Nykra service from its own checkout:

~~~sh
python -m nykra serve
~~~

Its token is generated automatically in the per-user Nykra data directory. The Node bridge discovers the token at the same location, then sends authenticated JSON to `127.0.0.1:8765`. It never transmits the token to ChatGPT or over the MCP tunnel. The service may be started separately during development; a later self-contained installer will manage its lifetime.

**The bridge never forwards tool arguments, command strings, file names, prompts, stdout, stderr, or tool results.** Only these fields are sent: stable event ID, local source name (`relai`), tool name, task ID if present, outcome, and duration. Activity is separately stored from scored discovery candidates.

Failed service requests are dropped rather than changing, failing, or delaying the underlying agent call. A bounded maximum of 64 outstanding sends prevents indefinite work accumulation. `observer.stats` exposes local diagnostic counters only. An unavailable daemon does not block Rel.AI.

## Important limitations

- This is **passive integration**: it observes tool completions. A tool completing successfully is **not proof** that a solution is correct or better.
- Rel.AI's event stream does not automatically expose a search tree or hidden agent reasoning. A later supervised discovery runtime or explicit evaluator hook will be required to create scored tree edges with valid parent/child relations.
- The host must load the bridge. A Python package alone cannot modify a remote MCP client's tool behavior.
- Activity may be dropped if Nykra is offline or on abrupt shutdown. At-least-once durable delivery is future work; stable operation IDs allow idempotent resubmission.
- Installing this in a host build is a one-time **host integration**, not a per-agent configuration. It has not yet been merged into or activated inside the independent upstream Rel.AI project.
- Only data from authorized host workspaces should be instrumented. Keep the existing Rel.AI authorization and privacy boundaries; do not intercept unrelated system activity.

## Reproduce bridge tests

From the Nykra repository root:

~~~sh
python -m unittest discover -s tests -p test_relai_bridge.py -v
~~~

The test starts a real Nykra localhost server, creates a fake host listener, emits event objects matching Rel.AI's documented source interface, and verifies ingestion, duplicate suppression, privacy exclusions, and fail-open behavior. It does **not** claim to be a test against a production Rel.AI process.
