# Nykra v0.21 — Actionable public-test feedback experiment

## Question

Can a coding agent repair a real historical defect more reliably when given a **short, sanitized public regression diagnostic** instead of only a Boolean public pass/fail result?

This is a **feedback-quality comparison**, **not** an experiment showing superiority of Nykra's adaptive exploration policy. Both arms revise the **same model-generated initial candidate**, using the same authenticated `gpt-6-luna` low-effort inference backend with one 70-second continuation call per arm.

## Intervention and reusable implementation

The new reusable `nykra/repair_feedback.py` classifies syntax errors, wrong replacement format, function signature changes, and oversized source as **model-invalid** before invoking Docker. It keeps evaluator/image/build/timeouts separate from publicly tested semantic failures.

The new grader `nykra/v21_grader.py` uses pinned local Python 3.8 Docker images, no network, nonroot UID, read-only root filesystem, dropped capabilities, no-new-privileges, CPU/memory/PID quotas, no host mounts and timeouts. Public regression failures can produce a 900-character maximum diagnostic stripped of file paths, control characters and ANSI sequences. Hidden suite outcomes and logs are **never returned to model prompts**. Docker confinement is not certified to handle adversarial code.

Each task uses one common candidate and public grade. Only when that candidate fails due to a *model patch* or the public test do both arms receive one call:
- **Bare arm:** previous candidate and public status only.
- **Enriched arm:** identical previous candidate and status, plus the bounded public diagnostic.

Both arms run before final hidden tests. Paired task order alternates as frozen. Missing evaluator infrastructure is excluded rather than scored against either arm; an initial publicly passing repair is separately hidden-verified and gives neither arm a win.

## Frozen real-issue protocol and pre-inference amendment

The [amended protocol](evidence/v21_protocol.json) was frozen before any v0.21 Codex repair calls. Six previously unused historical BugsInPy bug IDs were selected in the upstream **youtube-dl** repository: 24, 25, 27, 28, 29 and 43. The original [protocol](evidence/v21_protocol_initial.json), [hidden-check specification](evidence/v21_hidden_spec_initial.py), and [first reference preflight](evidence/v21_prevalidation_initial.json) are retained.

A reference-only preflight exposed obsolete private upstream test selectors for three historical commits and flawed or nondiscriminating private oracle cases in two issues. Before any model calls, non-existing unrelated selectors were removed, the out-of-range HTML entity case was corrected, and a numeric-JS case was added. The [amended reference preflight](evidence/v21_prevalidation.json) succeeded on **five of six**: the genuine buggy source failed public and hidden checks while the upstream repaired source passed both. **Bug 25 remains excluded** because the revised hidden oracle still failed on the reference fix. No additional edits were made after viewing model results.

## Actual results

| Real issue | Common first model candidate | Bare revision | Actionable-feedback revision |
| --- | --- | --- | --- |
| youtube-dl 24 — numeric-string matching | **Public + hidden pass** | Not called | Not called |
| youtube-dl 25 — JS numeric literals | **Ineligible hidden reference** | Not called | Not called |
| youtube-dl 27 — subtitle timestamps | Public fail | Public fail | Public fail |
| youtube-dl 28 — invalid HTML entities | **Public + hidden pass** | Not called | Not called |
| youtube-dl 29 — unknown dates | **Public + hidden pass** | Not called | Not called |
| youtube-dl 43 — URL basename | Public fail | Public fail | **Public + hidden pass** |

The public failure diagnostic in the v0.21 bug 43 shared candidate identified the concrete assertion mismatch: `AssertionError: '' != 'trailer.mp4'`. Only the enriched arm received that diagnostic. Its generated revision passed the public regression and the separate hidden behavioral suite; the status-only arm failed.

**Eligible tasks:** 5/6. **Shared hidden-verified first-attempt repairs:** 3. **Genuine paired feedback comparisons:** 2. **Full hidden-verified successes:** enriched **1/2**, bare **0/2**; one enriched-only win, zero bare-only wins. The exact two-sided paired sign p-value is **1.0** due to the single discordant task. This is far too small to establish a reliable success-rate improvement.

Among paired continuation calls, total model-reported tokens were **3,826 enriched** versus **16,760 bare**. That difference is descriptive and dominated by variable model sampling; no token-efficiency or speed guarantee follows from two task pairs. The budget allowed at most one 70-second model call per arm with a soft reported-token cap; it did not enforce identical exact token counts.

Read the original completed raw runs: [24](evidence/v21_youtube_dl_24.json), [25](evidence/v21_youtube_dl_25.json), [27](evidence/v21_youtube_dl_27.json), [28](evidence/v21_youtube_dl_28.json), [29](evidence/v21_youtube_dl_29.json), [43](evidence/v21_youtube_dl_43.json), and their integrity-checked [machine summary](evidence/v21_summary.json). All original candidates, public grades, model output, token counters and independently verified hidden verdicts are retained.

## Research interpretation

This is **one new real-world hidden-verified repair attributable to the richer *information arm* in a matched shared-prefix comparison**, not proof of Nykra's adaptive policy or a general model improvement. Task population is small, restricted to one historical repository and one-function patches; benchmark training contamination is unknown; model continuations are stochastic, not seed-matched; and three tasks were already solved before feedback intervention.

### Next gate

Repeat a prospectively preregistered feedback arm comparison across more *unseen* repositories and patches, preferably with multi-file capability, issue-linked independent hidden tests, repeated samples per issue and strict model budgets where supported. Report initial solvability, invalid-patch rates, paired task successes and costs separately. No evidence supports automatically enabling enriched feedback across all agents yet.

No Git commit or push was performed. This is source-tree research implementation, not a new installed release.
