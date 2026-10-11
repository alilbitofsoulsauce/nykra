# Nykra v0.11 — Rel.AI-first AI Agent Loop

This is the **Rel.AI-specific integration** for Nykra's evaluated coding exploration. A connected ChatGPT or another AI agent may conduct the whole proposal → test → feedback → revision → held-out evaluation workflow **within one authorized conversation/task**, using existing Rel.AI MCP execution and file-editing tools. It requires no separate per-agent MCP server, no patched Rel.AI host, and no broken agyc CLI.

## What it does and does not automate

Nykra selects each requested exploration action, executes restricted Python candidate code, returns at most three **training-only** failing cases, tracks observed candidate-parent links, and automatically tests the best evaluated code on held-out inputs when a passing score or candidate budget is reached. The connected AI agent creates each code proposal as requested. This removes the need for a human to manually coordinate every revision **while a connected AI agent is already executing a user-authorized turn**.

The currently installed Rel.AI host is an MCP workspace/tool and task orchestration environment; it **does not expose a verified model-inference endpoint that Nykra can invoke**. Therefore this workflow **cannot produce new model-generated candidates independently after the ChatGPT turn ends**. It does not run a permanently unattended LLM service, train model weights, or alter hidden reasoning. Universal and independent model adapters remain later work.

## Invoke from a Rel.AI-connected agent

The agent begins a normal Rel.AI work session in the authorized nykra workspace and requests the Nykra integration instructions as needed. One prompt can ask the agent to complete the following until the session finishes or budgets expire:

1. Execute the start command through Rel.AI:

       python -m nykra relai-agent start --task balanced-brackets --policy depth --budget 4 --max-seconds 1200 --approve

2. Read the returned session ID, requested kind, and task description. Generate exactly **one complete Python solve(...) function** as a source file, using a trusted Rel.AI file-editing tool. No imports, attribute access, unauthorized IO or external network use.
3. Execute:

       python -m nykra relai-agent submit --session SESSION_ID --candidate-file candidate.py --approve

4. If state is awaiting_agent, inspect the returned feedback and next request. A revise request includes the **parent_source** to revise, so a new model prompt or old source file does not need to be manually retrieved. New_root requests an independent candidate. Replace the agent-owned candidate file with the next implementation and repeat step 3.
5. If state is finished, the best previously scored candidate was evaluated on held-out tests. Report the observed training progression, final held-out score, attempts, test scope and limitations. Do not claim improvement of search policy or general model capability from one task.
6. On any fatal condition, run an explicitly approved abort command to mark the trial failed and clear managed candidate source files:

       python -m nykra relai-agent abort --session SESSION_ID --approve

If an agent turn is interrupted, it can recover the requested action by calling:

    python -m nykra relai-agent next --session SESSION_ID

If all attempts were used but auto-finalization was interrupted, use:

    python -m nykra relai-agent finalize --session SESSION_ID --approve

**Approval scope:** The connected user must have authorized this bounded code-evaluation task. A Rel.AI-connected assistant must not infer authorization for arbitrary repositories, cloud execution, billing, reading credentials or unsafe shell commands merely because this command accepts --approve.

## Optional prospective policy trial

Use the existing prospective protocol with evaluator ID nykra-coding-fixtures-v1, objective maximize and fixed thresholds/budgets. Pass matching --trial TRIAL_ID and --task-key UNIQUE_TASK_KEY to relai-agent start. The preassigned breadth/depth/adaptive arm overrides the command's policy. The terminal held-out result is submitted to the prospective ledger automatically.

This is **not valid evidence of strategy improvement** until new, independently defined task sets with sufficient arm sizes and independent evaluator outcomes are collected.

## Temporary source handling

Previous versions did not store candidate source in Nykra at all, requiring the AI to resend the best code for finalization. v0.11 deliberately introduces a **small, local, per-session source cache** under the user-profile Nykra state directory in relai-agent-cache/SESSION_ID. Each complete source is limited to 4,500 UTF-8 bytes; session and attempt filenames are generated 32-digit hexadecimal IDs. Cached source is supplied back only to the same local authorized session, allowing model revisions to reflect the selected parent and automatic finalization of an earlier best candidate.

This is **temporary source persistence**: Nykra clears .py candidate files on successful finish or abort; the ownership marker and local lock may remain for diagnosis. If an agent is forcibly terminated before either operation, the cache remains to permit recovery. The caller's separately authored candidate.py also remains in the workspace until explicitly removed by the caller. Cached sources are not written to Nykra's SQLite histories and are not sent to a cloud provider by Nykra. A user-level filesystem adversary can still read same-user files; this mechanism does not encrypt source code.

## Validation and limitations

The focused v0.11 tests cover approval, feedback-driven success, best-of-budget finalization, durability across separate Python objects/processes, CLI execution, tampering and path traversal, abort cleanup and prospective accounting. They operate in isolated temporary Nykra homes and do not modify active Rel.AI.

A real connected-model smoke test on October 11, 2026 used two model-authored bracket-checking implementations, evaluated the initial code at 14/18 training cases, returned examples including the invalid string ([)], selected a depth revision, and automatically finalized the corrected function at 18/18 training and 32/32 held-out cases. This is a real **model-in-the-loop tool workflow**. It is neither fully unattended background model inference nor a general benchmark.

The restricted Python worker runs a subprocess with timeouts, no imports, and a small AST allowlist, but **is not a security sandbox**. Do not run intentionally malicious code. The three current coding fixture families are too narrow and public for claims of real-world coding-agent generalization. Hardened isolation and independent blind benchmarks are still necessary before attempting unattended deployment.
