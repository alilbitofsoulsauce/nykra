# Changelog

## 0.26.0 — Release candidate prepared, not yet published

- Added an approval-gated, provider-neutral supervised multi-file coding workflow and bounded structured source-edit to Git-diff adaptation.
- Added offline provider readiness/safety checks, precise same-request/public-evaluation caching, and fail-closed malformed-Unicode handling.
- Recorded independent historical coding trials through research v0.40, including **negative adaptive-policy outcomes** and task-specific structured-edit improvements. These do not establish a general coding success-rate increase.
- Extended clean-clone CI, pending-file release hygiene, package/extension version checks and an offline release-candidate wheel smoke.
- Preserved the original v0.37 benchmark-era adapter and test-source bytes alongside current hardened source, without rewriting historical outcomes.

This entry describes an **unreleased local candidate**. The published tag remains v0.25.0 until GitHub-hosted checks, maintainer review and an explicit release action are completed. See [release-candidate checklist](docs/RELEASE_CANDIDATE_V026.md).

## 0.25.0 — Source-tree multi-file transaction milestone

- Added strict allowlisted multi-file Git patch preflight, disposable local Git checkout, real passing/failing test execution, exact tested-byte promotion and rollback on promotion errors.
- Added a user-visible patch-transaction CLI, with pinned restricted Docker as default and separately authorized trusted local test mode.
- Added adversarial tests covering two interacting source fixes, path and symlink attacks, malformed diffs, file add/remove, CLI transport, clean worktree requirements and failure recovery.
- Added a reproducible **seeded synthetic two-file** Docker repair trial. This demonstrates patch-workflow correctness only; it does not establish improved model coding ability.
- Preserved v0.24 independent-session public-result caching evidence and earlier null real-issue policy comparisons without pooling those results.
- Improved OSS release documentation and fresh-clone CI scope.

## Earlier experimental milestones

- v0.24: cross-session exact-source/evaluator public Git/Docker cache; 6 versus 2 actual Docker calls in two reused historical cases; no extra inference or model correctness gain.
- v0.23: verified shared-prefix receipt reuse; 14 versus 8 real public Docker calls across two reused cases; correct outcomes unchanged.
- v0.22: Rel.AI-hosted portable real upstream Git-patch workflow; 8 actual Codex completions, 14 Git patch instances, both policy arms solved 1/2 reused tasks.
- v0.21: matched public feedback comparison; one enriched-only hidden-verified repair among two paired issues, too few for general conclusions.
- v0.20: independent real-issue replication found no policy advantage on its eligible fork set.

See docs/EVIDENCE.md for all raw files and limitations.
