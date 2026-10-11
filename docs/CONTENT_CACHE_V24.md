# Nykra v0.24 — Persistent exact-source public evaluation cache

## What now works

Nykra can reuse real, previously verified public Git/Docker test results **across independently created agent sessions**, even when they use different exploration policies, feedback configurations, or prompt ancestries. This extends the v0.23 optimization, which could only reuse identical branch histories.

The implementation is opt-in, local and agent-neutral. **ChatGPT can author a proposal and Rel.AI can submit and test it without calling Codex.** The cache does not generate model answers, make external inference requests, or claim token savings.

### Security and validity boundary

A candidate is first checked as a correctly named, one-function Python source with the original signature. A content-addressed key covers its exact bytes, the original and patched Git source hashes, the public upstream regression test source and selector, historical Git revision identifiers, frozen evaluator protocol and evaluator implementation hashes, and the pinned Docker base-image ID.

On a cold miss, Nykra **actually** verifies and applies the Git patch in a disposable upstream checkout, runs the isolated public Docker regression, and persists a trusted local receipt for a successful public test or deterministic public regression failure. On a hit, Nykra recomputes the candidate's deterministic Git diff, compares exact source and input hashes against the stored receipt, validates the pinned local Docker base image, and reuses only that **public** result.

The target session receives the same diff with a separate exact source/patch hash and a cache-hit marker, but has **zero additional Git applications and zero public Docker runs**. The final hidden evaluator is still invoked independently after the workflow ends for every publicly passing session.

The cache refuses or avoids reuse when the task, code, test, evaluator implementation, public grading selector, source bytes or Docker image differs; if the cache file is corrupted or its checksum fails; if the source is malformed; or if the previous failure was an evaluator/infrastructure failure. The opt-in uses a bounded advisory lock around identical cache keys.

**Security limitation:** This is a **trusted local-user cache**, not a certificate or malicious-host-resistant signature. SHA-256 detects accidental modification and mismatch, but does not prevent a process with unrestricted access to the same workstation user files from forging both data and its checksum. Arbitrary hostile patches still must not be treated as safely sandboxed by default.

### How to use with free Rel.AI + ChatGPT

Rel.AI transports and executes proposals that ChatGPT authors in the current conversation. No Codex CLI is necessary for this path.

Start a session:

\`\`\`bash
python -m nykra workflow start --task youtube-dl-43 --policy adaptive --budget 4 --approve
\`\`\`

Read the agent request with \`workflow next --session SESSION_ID\`, write the generated full function source into a UTF-8 candidate file, then submit:

\`\`\`bash
python -m nykra workflow submit --session SESSION_ID --candidate-file candidate.py --cache-public --approve
\`\`\`

The \`--cache-public\` flag **must be supplied on each submission that should use the persistent cache**; without it the original uncached workflow remains the default. Subsequent independent sessions that submit identical code for the same pinned task/evaluator get a real receipt hit. This feature requires the registered real-issue source, its prevalidated public/hidden tests and local pinned Docker image. It is **not yet a general arbitrary multi-file Git repository cache**.

The older \`workflow reuse --session TARGET --verified-session SOURCE --approve\` still works for stricter matching-ancestry branch reuse. The new persistent cache is broader: the source and evaluator must match, but agent prompts and policy branches need not.

## Frozen real Git/Docker benchmark — zero new model calls

The [pre-frozen v0.24 protocol](evidence/v24_protocol.json) selected two historical BugsInPy \`youtube-dl\` issues already evaluated in earlier Nykra research. It selected actual prior model-authored source and fixed condition order **before these runs**. No new Codex or other model inference occurred.

For each real issue, three new, independent session instances—depth with enriched feedback, adaptive with status-only feedback, and breadth with enriched feedback—replayed the *same* archived candidate source. The baseline performed all three genuine Git applications and public Docker tests. The cached condition performed one cold evaluation and two independently validated warm hits. Issue execution order was counterbalanced. All publicly passing sessions received their **own actual hidden Docker evaluation**.

| Historical real issue | Ordinary Git/public Docker | Cache Git/public Docker | Ordinary elapsed | Cache elapsed | Hidden outcomes in each condition |
| --- | ---: | ---: | ---: | ---: | --- |
| youtube-dl bug 27 | 3 | 1 | 37.8773 s | 10.6953 s | 0/3 successful |
| youtube-dl bug 43 | 3 | 1 | 31.9037 s | 21.9699 s | 3/3 successful |
| **Total** | **6** | **2** | **69.7810 s** | **32.6652 s** | **All outcomes preserved** |

**Real measured engineering savings:** four of six public Docker executions **avoided (66.7%)**, four of six disposable Git applications **avoided (66.7%)**, and **37.1158 seconds shorter observed elapsed time (53.2%)** in these two local runs. Nykra recorded **four verified cache hits**.

The speed reduction is a **local observation**, not a guaranteed 53.2% speedup: there are just two previously seen historical issues, a single run per condition, Docker warm-up and machine load effects, and all model outputs are fixed from prior work. This is **not** evidence that Nykra repairs more real bugs or saves ChatGPT model tokens. A new, unrelated source cannot hit this exact-source cache.

### Independent process/CLI check

A separate full \`start → submit --cache-public → finalize\` run on a previously seen, publicly failing source executed the actual Git/Docker test once and reused the persistent result in an independently created second session. The second CLI submission made **zero new public Docker calls and zero Git applications**, while preserving the failure. This independently verifies the deployed CLI flag, not model improvement. See [external CLI evidence](evidence/v24_cli_independent_control.json).

## Evidence and reproducibility

- [Frozen protocol](evidence/v24_protocol.json)
- [Machine-recomputed summary](evidence/v24_summary.json)
- [Bug 27 cold/warm raw sessions](evidence/v24_cache_youtube_dl_27.json)
- [Bug 43 cold/warm raw sessions](evidence/v24_cache_youtube_dl_43.json)
- [Twelve exported session states and Git patches, SHA index](evidence/v24_session_export_index.json)
- [Two exported original real public Docker receipts, SHA index](evidence/v24_public_receipt_index.json)
- [CLI independent-process control](evidence/v24_cli_independent_control.json)

The cache lives under ignored \`experiments/public-receipts-v24/\` for ordinary local workflow use. The benchmark uses its own isolated ignored cache namespaces to avoid previously warmed results. Exported public receipts and source files are saved in \`docs/evidence\` for audit, without hidden test bodies in the cache itself.

No user repository was modified. Nothing was committed or pushed. The installed passive workstation observer is still v0.16; this is source-tree v0.24 functionality.

## What comes next

A future general-purpose Nykra cache needs robust permissions for arbitrary repositories, multi-file patch support, isolation validation for untrusted dependencies, a storage quota/eviction policy, and independent task-disjoint performance tests. Separately, whether Nykra's adaptive exploration *improves code correctness* remains unproven and must be studied with new tasks and genuine controlled forks.
