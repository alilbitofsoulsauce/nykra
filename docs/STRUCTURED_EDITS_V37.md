# v0.37 — Structured exact edits beat raw Git-diff serialization on an unused historical bug

## Verified result

Nykra's **structured source-edit adapter** repaired a previously unused
BugsInPy historical issue, **youtube-dl #32**, using one authenticated
Codex **GPT-5.6 Luna** completion. The model returned bounded JSON
replacements. Nykra generated a correct two-file Git patch with computed
hunk ranges, then the original upstream public regression and five
separately frozen hidden tests passed in restricted pinned Docker.
A wholly separate real public-and-hidden Docker regrade of the
exact patch also passed.

The independent **raw Git-diff** baseline generated **12 completed
Luna responses**; every resulting patch was invalid or could not apply
to the historic Git source, so no baseline patch reached Docker. The
baseline command was **operator-stopped**, not solved. Its checkpoint
remains intentionally `running` because it did not terminate normally.

| Actual outcome | Raw Git diff | Structured edits |
| --- | ---: | ---: |
| New independently generated Codex completions | **12** | **1** |
| Invalid or non-applicable Git proposals | **12** | **0** |
| Actual public Docker grading calls | **0** | **1** |
| Actual hidden Docker grading calls | **0** | **1** |
| Public pass | No applicable source | **PASS** |
| Hidden pass | Not run | **PASS** |
| Independent public-and-hidden regrade | Not possible | **PASS / PASS** |
| Model-reported input tokens, including cached | **336,716** | **15,140** |
| Model-reported output tokens | **9,989** | **711** |
| Modified production files | 0 evaluated | **2** |
| Terminal outcome | Operator interrupted | **Verified solved** |

The baseline used **321,576 more input tokens** and **9,278 more output
tokens** without producing a valid source patch. These are **actually
used tokens**, not tokens saved in a controlled solve-to-solve comparison.
Because baseline did not solve, there is no defensible relative
time-to-solution ratio. The task was used only once here; this finding
does not prove a general uplift rate.

## Exact frozen source and test provenance

- Upstream origin: BugsInPy `youtube-dl` bug #32, previously unused
  in Nykra evidence; original commits from the locally cloned
  upstream repository.
- Allowed production paths:
  `youtube_dl/extractor/npo.py` and `youtube_dl/utils.py`.
- Failure: NPO extractor metadata payload `parseMetadata(JSON)` with
  trailing JavaScript comments must be transformed into JSON while
  existing JSONP behavior remains intact.
- Pre-registered public upstream check:
  `test.test_utils.TestUtil.test_strip_jsonp`.
- Five evaluator-owned hidden checks also exercise the NPO extractor
  integration and legacy JSONP behavior. These were **frozen before
  any v37 Codex call**, SHA-256
  `fc9a13980580d3e121c65b7d746973b14f412dad4d7ba29bf62812e29e4ed745`.
- All four real source prevalidation paths were checked before
  model calls: buggy public and hidden **FAIL**, official reference
  public and hidden **PASS**.
- Frozen study protocol SHA-256
  `77965e4d6d27afb580f4c128744df3a5ad420b514a5ef18da11f91babfe985e6`.
- Two arms had the same Codex model/authentication, historical Git
  revision, public test, hidden verifier, file allowlist and task
  context. The purposeful intervention was the **output format**:
  model-authored Git hunk headers versus JSON exact source replacements
  converted into diff hunks by Nykra.
- The previous v0.36 study found raw Git patch construction the
  central repeated blocker; this intervention was chosen *before*
  the v37 model calls. It is a new issue, not a rerun of #35.

## Implementation

`nykra/structured_edit_adapter.py` accepts only JSON objects with
an `edits` array of up to twelve dictionaries containing exactly
`path`, `old` and `new`. Each original span must appear **exactly
once** in a pinned source file, and edit spans must not overlap. The
adapter rejects unregistered paths, test-file edits, ambiguous old
spans, no-op modifications, control characters, CRLF changes,
oversized requests, invalid UTF-8 originals and unsafe generated
patches. It builds the unified diff deterministically, verifies it
against Nykra's Git patch allowlist parser, and never executes
generated source or edits the original repository. The Docker grader
then independently checks actual Git application and tests.

The live provider runner `scripts/run_structured_codex_v37.py`
records the unmodified model response, the generated diff,
SHA-256 identities, exact public or hidden decisions, input/output
token receipts and controller checkpoints.

## Boundaries and interpretation

**What is demonstrated:** real useful work was recovered by an
agent-neutral source serialization adapter; a fresh historical
two-production-file repair reached independent hidden verification
on its first structured Codex proposal, while twelve different
raw-diff proposals were rejected by the Git patch checker.

**What is not demonstrated:** superiority of Nykra's adaptive
exploration policy (both arms in v37 use depth policy), a statistically
general accuracy uplift, an official SWE-bench result, a zero-dollar
financial savings claim, or a speedup ratio across two *completed*
solves. The format prompts necessarily differed. Baseline stopping
was a deliberate operator decision made after repeated malformed
patches, not a rate-limit failure; do not claim baseline can never
solve. This is a historical issue with potential model pretraining
contamination. Locally authored hidden cases are frozen and
independent of model responses, but not a third-party blinded
benchmark.

## Evidence and rerun instructions

- `docs/evidence/v37_structured_multifile_protocol.json`
- `docs/evidence/v37_hidden_npo_jsonp.py` — evaluator-only
- `docs/evidence/v37_multifile_preflight.json`
- `docs/evidence/v37_structured_live/youtube-dl-32_baseline_raw_git_diff.json`
- `docs/evidence/v37_structured_live/youtube-dl-32_nykra_structured_adapter.json`
- `docs/evidence/v37_structured_independent_regrade.json`
- `docs/evidence/v37_structured_summary.json`
- `nykra/structured_edit_adapter.py` and `nykra/v37_multifile_grader.py`
- `scripts/run_structured_codex_v37.py`
- `tests/test_structured_edit_adapter.py` and
  `tests/test_v37_structured_live.py`

Run only in the authorized Nykra workspace with preinstalled
pinned Docker and authenticated ChatGPT Codex. Neither a Git
commit nor push nor any patch promotion is part of the study.
