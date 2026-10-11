# Security policy

Nykra is experimental, local-first agent-workflow infrastructure. It can execute tests, apply Git patches and run local subprocesses with explicitly granted permissions. **Do not interpret a passing security test as proof that arbitrary agent-written code is safe to execute.**

## Reporting a vulnerability

Use GitHub's private vulnerability reporting / Security Advisory interface for the repository if enabled. Do not publish working exploits, credentials, private workspace contents or personally identifying diagnostic logs in public issues. If private reporting is unavailable, open a public issue containing only a high-level security concern and request a private contact channel.

## Supported components

The current repository source is maintained on the main branch. The previously installed v0.16 observer and the v0.25 source tree may differ; report which version and command you used. No contractual security-fix SLA is promised.

## Trust boundaries

- Safe by default: Nykra observes local history read-only. Real repairs require explicit approval and task allowlists.
- Git patch trials: only clean committed checkouts, allowlisted text paths and tested bytes are eligible for promotion. Original state is restored on failed promotion when possible.
- Container test execution: pinned image IDs, network disabled, read-only container root, nonroot UID, dropped capabilities and resource caps are protections, **not** a certified adversarial sandbox.
- Trusted local tests: these execute arbitrary repository code with the local user's OS permissions. Do not use for untrusted patches.
- Persistent receipt cache: checksum and exact-input checks detect mismatches, but a process with full write access to the same account can forge receipts and checksums. Avoid shared hostile-user workspaces.
- Agent drivers: ChatGPT/Rel.AI controls proposal and command authorization. Nykra does not provide or require separate Codex credentials.
- No automatic commit, push, deployment, shell hooks or privilege escalation is part of the patch-transaction engine.

## Disclosure hygiene

Never attach auth tokens, private keys, signed URLs, local database state, hidden test code from closed-source providers, or proprietary repositories to an issue. Before attaching a minimal reproducer, scrub absolute workstation paths, emails and environment values.
