# Nykra v0.12 — Agent driver portability

Nykra Core is independent of Rel.AI. The new `nykra.drivers.AgentDriver` Protocol formalizes the explicitly approved request/submit/feedback/abort lifecycle. Host-specific agents may implement this contract without migrating Nykra's local evaluation, replay, activity store or policy framework.

## Supported driver levels

`python -m nykra integrations scan` discovers supported host binaries but **does not install plugins, patch applications or imply authentication**.

| Driver | v0.12 status | Actual evidence |
| --- | --- | --- |
| Rel.AI | Verified supervised connected-agent turn | ChatGPT proposes Python solutions through Rel.AI; Nykra requests branches and evaluates them. Rel.AI itself is not a model provider. |
| Codex | Discovery only | The Codex SDK supports persistent threads and streamed events, but no Nykra native Codex adapter has been implemented or validated. |
| Claude Code | Discovery only | An authorized future SDK/CLI adapter is possible; not installed or verified here. |
| OpenCode | Discovery only | The CLI and auth file may be detected, but unattended model inference has not been verified on this workstation. |
| Gemini CLI | Discovery only | Future native hooks require separately verified implementation. |
| Cursor | Discovery only | IDE CLI detection is not agent-runner control. |

**Only Rel.AI supports Nykra's complete supervised turn lifecycle in this release.** The `autonomous_generation` and `auto_policy_application` capability flags default to false. A detected executable is not equivalent to a working authenticated model service or an approved connection.

## Driver contract (Python)

```python
from nykra.drivers import AgentDriver, get_driver, scan_drivers
from nykra.store import HistoryStore

print(scan_drivers())
host: AgentDriver = get_driver("relai", HistoryStore())
started = host.start(task_id="balanced-brackets", policy="depth",
                     budget=4, max_seconds=1200, approval=True)
```

All candidate generation happens in the authorized host. The driver interface supplies only approved task context and scores to Nykra's independent evaluation loop. It does not grant every agent access to all workstation files, other connected systems or private model reasoning.

The core intentionally raises an error if users try to acquire an unimplemented `codex`, `claude` or `opencode` driver. Future adapters must demonstrate a real resumable model thread and safe tool restrictions before they can advertise interactive revisions or unattended generation.

## Research basis

- [Codex SDK README](https://github.com/openai/codex/blob/main/sdk/typescript/README.md): persistent, resumable threads and streamed agent events over a CLI-backed TypeScript SDK.
- [Codex app-server architecture](https://openai.com/index/unlocking-the-codex-harness/): a JSON-RPC driver interface and durable thread management.
- [OpenCode SDK](https://docs.opencode.ai/docs/sdk/): programmatic client and local server.
- [OpenCode permissions](https://dev.opencode.ai/docs/permissions/): explicit approve/deny configuration for agent tools.

These are architectural references, not proof that Nykra is already integrated with these agents.

## Install / removal

The existing per-user Nykra Windows installation is unchanged in its architecture: the background runtime **observes** allowed Rel.AI activity, and the CLI offers explicitly approved coding experiments. The new driver discovery is read-only. There is no per-agent configuration file, no implicit agent installation and no automatic model billing.

## v0.22: portable real Git repair workflow (additional interface)

The older `AgentDriver.v1` fixture-level API above is unchanged. A **separate and more practical source-tree workflow** now exposes `python -m nykra workflow start/next/submit/finalize` as a stable JSON exchange. A Rel.AI-connected agent can supply a complete function source file from one turn to the next; Nykra independently checks a Git patch in a disposable pinned upstream checkout, runs the registered public Docker regression, and reserves hidden grading until finalization.

An authenticated Codex CLI can also be used as a **read-only proposal provider** under the same Rel.AI-hosted workflow through `python -m nykra workflow auto ... --approve`. This is a working Codex inference *provider*, **not** a verified native implementation of the older `AgentDriver.v1` thread API. Native unattended Rel.AI inference, multi-file agent editing and tested native Claude/Gemini/OpenCode adapters remain unavailable.

[Detailed workflow usage, completed two-task integration smoke and retained source patches](AGENT_WORKFLOW_V22.md). Both depth and adaptive solved **1/2 previously reused historical issues** in the controlled integration smoke; no causal model-policy effect or general coding-agent gain was demonstrated.

### Next verification

A second real native adapter (Codex is preferred) must prove the same `start -> propose -> evaluate -> revise -> finalize` lifecycle in independent isolated workspaces, with error recovery and no reliance on Rel.AI. Then a sufficiently broad blind coding benchmark should compare that same model with Nykra enabled versus disabled at equal attempt and resource budgets. Only such evidence could begin to support a general coding-agent performance claim.
