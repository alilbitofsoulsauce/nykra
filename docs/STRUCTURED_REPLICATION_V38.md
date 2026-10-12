# v0.38 — Prospective replication of structured source edits

## Result

Two **previously unused historical multi-production-file BugsInPy issues** were
pre-registered before live Codex proposals. Both arms used the same
ChatGPT-authenticated GPT-5.6 Luna model, depth policy, underlying source,
upstream public regression, independently frozen hidden checks, and **five
new recorded model completions maximum per issue**. The controlled difference
was output formatting: the raw Git-diff baseline had to author hunk counts and
source context; Nykra received bounded JSON exact source replacements and
constructed diffs deterministically.

| New issue | Raw Git diff | Structured edits | Verification |
|---|---|---|---|
| youtube-dl #33, DRTV / fractional ISO8601 timestamps | 5 calls, 5 invalid patches, **0/1 verified** at limit | **1 call, 1/1 verified** | Upstream public + hidden, independent second Docker regrade |
| youtube-dl #31, Minhateca / duration unit parsing | 5 calls, 5 invalid patches, **0/1 verified** at limit | **2 calls, 1/1 verified** | Public fail on first valid candidate, then public + hidden pass on second; independent second Docker regrade |
| **Two-issue total** | **10 calls, 0/2 verified** | **3 calls, 2/2 verified** | Independent hidden tests twice on each selected repair |

The winning structured candidates each changed both registered production
files, not just the shared utility. The #31 first structured candidate was
an *applicable* two-source patch which failed the upstream public suite;
the second model response revised it to pass. No hidden feedback was
provided to either coding arm.

## Directly measured work

| Measured field | Raw Git-diff baseline | Nykra structured edits |
|---|---:|---:|
| Recorded new Codex completions | 10 | 3 |
| Provider-reported input tokens, including cached | 306,683 | 47,023 |
| Provider-reported output tokens | 8,117 | 1,964 |
| Invalid/non-applicable patches | 10 | 0 |
| Actual public Docker evaluations | 0 | 3 |
| Original independent hidden Docker evaluations | 0 | 2 |
| Hidden-verified repaired issues | 0 | 2 |
| Sum of live CLI model-call wall seconds | 206.283 | 59.610 |

The raw-diff cohort spent **259,660 more input tokens** and
**6,153 more output tokens** within the trial, but did not solve
the issues at its pre-registered **five-call cap**. Consequently a
*solve-to-solve* percentage time or token saving is **not measurable**.
All rates refer to these two historical tasks and this model.

## Frozen protocol and real source checks

Frozen before any v38 completion:

- Protocol: `docs/evidence/v38_cohort_protocol.json`, SHA-256
  `3370cda8492374555b2e2696a292b7be5fa9b9072dae36ff03f94a3acaa27df3`.
- Hidden #33: `docs/evidence/v38_hidden_drtv_33.py`, SHA-256
  `7cceb4db384a91cd50ccc0a51cb8258adfaefd4f62e86e1d82cea1422ad13b2e`.
- Hidden #31: `docs/evidence/v38_hidden_minhateca_31.py`, SHA-256
  `ca77170c572d8a7730c98db019731a647c8f493964fdc0322e0ebf9a2d75879b`.
- Eight real pinned, offline, restricted Docker preflight checks in
  `docs/evidence/v38_preflight.json`: for **each issue**, original buggy
  public **FAIL**, buggy hidden **FAIL**, official fixed public **PASS**,
  fixed hidden **PASS**.
- `docs/evidence/v38_independent_regrade.json` records four additional
  real public+hidden Docker sessions: **PASS/PASS for both selected repairs**
  with **zero further model calls**.

Both study arms were allowed the same depth revision mechanism and the
same public-only feedback. Different JSON-vs-unified-diff formatting
instructions are integral to the studied intervention, not a hidden
model capability change.

## Reliability incident and exclusions

Two Codex CLI executions were attempted on #33 before the first
usable paired sample:

1. The earlier Windows helper decoded a Unicode response as CP1252,
   causing an exception before preserving any receipt.
2. After switching to explicit UTF-8, the new v38 grader initially
   referred to a wrong protocol configuration field. It failed after
   the provider response and before persisting the candidate.

Both incidents are recorded at
`docs/evidence/v38_pretrial_unicode_failure.json`. Either may have
consumed ChatGPT Codex plan allowance, and neither has complete usage
receipts. **They are not counted as benchmark coding completions, nor
claimed to be free.** The v38 runner now decodes UTF-8 explicitly and
durably saves each pending model completion *before* evaluator execution;
a grader exception can be resumed without a second provider call. The
frozen task protocol and test content were **not changed** after model
usage.

## Implemented capability and limits

The `nykra/structured_edit_adapter.py` adapter from v37 remains
unchanged. It rejects unregistered file paths, unsafe or oversized
strings, ambiguous source spans, overlaps, no-ops and malformed JSON.
It deterministically generates a real Git patch from exact original
source replacements. The v38 multi-task grader runs generated source
only within restricted, networkless Docker on an independently verified
base image; it does not apply a candidate to the Nykra repository.

This replication shows **three consecutive newly selected historical
two-file issues** (#32 in v37 and #33/#31 in v38) on which structured
output yielded verified repairs within the recorded experiment, whereas
the raw diff path failed within the observation windows. That is
promising reproducible *workflow* evidence, not a proof of universal
superiority. Two new samples are too few for a reliable general
population success rate, all issues are historical (potential
training contamination), the hidden suites were authored locally
before inference rather than by an independent benchmark administrator,
and raw baselines were stopped unsolved.

Crucially, **this experiment did not test adaptive exploration**:
both arms used depth policy. The demonstrated intervention is
format adaptation, patch construction and evaluator feedback.

## Artifacts

- `docs/evidence/v38_cohort_protocol.json`
- `docs/evidence/v38_hidden_drtv_33.py` and
  `docs/evidence/v38_hidden_minhateca_31.py`
- `docs/evidence/v38_preflight.json`
- `docs/evidence/v38_structured_live/` (all four model traces with raw
  responses, hashes, Docker receipts, provider usage, and unsuccessful
  source proposals)
- `docs/evidence/v38_independent_regrade.json`
- `docs/evidence/v38_pretrial_unicode_failure.json`
- `docs/evidence/v38_results.json`
- `nykra/v38_multifile_grader.py`
- `scripts/run_structured_cohort_v38.py`
- `tests/test_v38_structured_cohort.py`

No Git commit, push, patch promotion or repository deployment occurred.
