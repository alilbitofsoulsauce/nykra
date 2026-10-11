# Nykra v0.22 — Rel.AI-hosted real coding workflow

## Working integration

Nykra now has an **approval-gated, durable host-neutral coding workflow** for registered real upstream Git issues, using the same pure exploration-policy engine as earlier synthetic experiments.

The first driver is **Rel.AI as the workstation execution host**. A connected ChatGPT agent can request the next action, write an authorized candidate source file, and submit it. Alternatively, an authenticated local Codex CLI can supply read-only inference proposals through the **same portable workflow API**, invoked by the Rel.AI execution host. Rel.AI MCP by itself **does not expose independent unattended LLM inference**.

This is a functional integration rather than a fully native universal multi-agent controller. Claude, Gemini, OpenCode and IDE adapters **are not connected through this workflow yet**.

### Source patch and evaluation boundary

Each registered real issue contains a pinned buggy upstream Git revision, a whitelisted Python function, and independent public and hidden test selectors.

For each submitted source:
1. Validate that the candidate is a single complete function with the correct signature and size. Invalid model source is distinguished from evaluator infrastructure failure.
2. Generate a standard unified diff against the **actual upstream buggy Git source** and run `git apply --check` followed by `git apply` in a fresh disposable Git archive. Confirm applied source bytes; normalize verified Git-for-Windows CRLF checkout differences to the canonical original LF bytes.
3. Save immutable per-attempt source SHA-256 and patch SHA-256, public grader status, public-only bounded diagnostic, parent ancestry, model usage (when available), and driver label.
4. Run the source repair in the prevalidated restricted Docker image: no network, nonroot, read-only root, dropped capabilities, no-new-privileges, CPU/memory/PID limits and timeout. Docker is **not certified for hostile arbitrary code**.
5. At the terminal selection, grade the earliest public-passing candidate exactly once on separate hidden behavioral/upstream tests. Do not expose hidden failures to subsequent agent prompts.

This workflow is currently a **single-function upstream repository patch** implementation, **not unrestricted autonomous multi-file modification of the user's working repository**. It never edits the real user's upstream checkout, triggers remote pushes or publishes patches.

### Agent-agnostic CLI over Rel.AI

An authorized connected agent can execute:

```bash
python -m nykra workflow tasks
python -m nykra workflow start --task youtube-dl-43 --policy adaptive --budget 4 --approve
python -m nykra workflow next --session SESSION_ID
```

The `start` and `next` commands return a structured request, selected parent, original source, bounded public feedback, and a prompt. A connected agent authors one full function into a UTF-8 file within the authorized workspace, then submits:

```bash
python -m nykra workflow submit --session SESSION_ID --candidate-file candidate.py --approve
```

Repeat `next` and `submit` until `agent_required: false`. Then finalize:

```bash
python -m nykra workflow finalize --session SESSION_ID --approve
python -m nykra workflow summary --session SESSION_ID
```

For interruption, `workflow next` can recover the current session from disk. `workflow abort --session SESSION_ID --approve` stops without hidden grading. For **Codex-provided automatic local proposals** (when its CLI is installed/authenticated), the Rel.AI host can execute the separately explicit opt-in command:

```bash
python -m nykra workflow auto --task youtube-dl-43 --policy adaptive --budget 4 --approve
```

The command does not claim to make Rel.AI itself invoke a model or to grant any third-party agent permissions. Driver-specific inference remains owned and authenticated by that driver.

Session source and patches are retained in `experiments/workflow-sessions/SESSION_ID/` for recovery and audit, so users must treat that directory as source-bearing. The v0.22 pilot copied only explicitly authorized sessions into `docs/evidence/v22_sessions/`; no secrets or unrelated workstation files were exported.

## Actual end-to-end model-driven trial

The frozen [v0.22 integration protocol](evidence/v22_workflow_protocol.json) selected **two historical BugsInPy youtube-dl defects already evaluated in v0.21**: bugs 43 and 27. This is an **engineering integration smoke**, not an independent benchmark or model-effectiveness study.

Both depth and adaptive controllers began from **one identical model-generated, actually Git-applied source patch per shared turn**. Model completion was invoked once, then its source was evaluated in both arms. If their actual policy decisions diverged, the same authenticated Codex backend generated one independent continuation per branch. Both arms used a four-attempt ceiling, identical public-only diagnostic mode and a 70-second per-model-call timeout.

| Historical issue | Unique Codex completions | Real Git-applied patch instances | Policy fork | Depth hidden result | Nykra adaptive hidden result |
| --- | ---: | ---: | --- | --- | --- |
| youtube-dl 43, URL basename | 3 | 6 | No, shared third attempt solved | **Pass** | **Pass** |
| youtube-dl 27, TTML timestamps | 5 | 8 | **Yes**: revise latest vs new root | Fail | Fail |
| **Total** | **8** | **14** | **1 actual fork** | **1/2** | **1/2** |

The bug 43 third candidate successfully repaired the upstream source and passed hidden grading on both branches. Bug 27's three common candidates failed; then the actual exploration-policy controller selected depth revision versus adaptive new root at the fourth call. Both failed publicly and had no eligible final hidden candidate.

**There is no observed coding-task success-rate advantage for Nykra.** The only actual fork failed for both arms. Model source and patch SHA-256 records, ancestry, task-specific public/hidden grade outcomes and token counters are preserved. Model-reported cumulative tokens for the shared bug-43 prefix were 24,315 in each arm (the **same** three inferences, not six independent calls). The total counts distinguish **8 actual model completions** from **14 application/evaluation instances**.

[Machine-audited report](evidence/v22_workflow_summary.json), [bug 43 raw comparison](evidence/v22_workflow_pair_youtube_dl_43.json), [bug 27 raw comparison](evidence/v22_workflow_pair_youtube_dl_27.json), and [portable session source/patch export index](evidence/v22_session_export_index.json). The export index verifies exact bytes of the model-generated patches and state logs independently of the live workstation directory.

### Independent-process CLI check

A separate controlled [CLI smoke](evidence/v22_cli_reference_smoke.json) executed `workflow tasks → start → next → submit → finalize` through new Python processes. It submitted the **upstream reference function**, produced a verified Git patch and passed public and hidden Docker tests. This is a **transport/reference control**, not a model-generated success, and is omitted from the table above.

## v0.23 verified duplicate-work elimination

[See measured savings and secure reuse protocol](WORK_SAVINGS_V23.md). The newer source-tree workflow adds `workflow reuse --session TARGET --verified-session SOURCE --approve` to avoid repeat Git apply and public Docker work on identical checked agent candidates. No model or external Codex token usage is required for the operation; unrelated proposals cannot be reused.

## v0.24 independently reused Git/Docker verdicts

[Measured exact-source caching and safety conditions](CONTENT_CACHE_V24.md). New opt-in CLI `workflow submit --session ID --candidate-file candidate.py --cache-public --approve` stores/reuses a checked local public Docker result across separate sessions with different policies and prior prompts when evaluator input is identical. The existing default remains uncached; hidden verification always remains separate. No new model calls are needed to reuse a cached result.

## What next

**v0.23** should add signed, explicit workspace permissions and a Docker-contained **multi-file unified-diff** repair protocol, create verified native adapters for other agent runtimes, and preregister genuinely *new* repository issues with multiple repeat samples and independent hidden grading. This will test whether the workflow actually improves coding throughput and correctness, rather than only whether a known narrow patch interface works.

**Release status:** Nykra's installed observer is still v0.16.0. These v0.22 workflow modules and CLI commands are implemented in the source tree; they are not a separately published universal agent runtime. No commit, push, cloud deployment or automatic user repository modification was performed.
