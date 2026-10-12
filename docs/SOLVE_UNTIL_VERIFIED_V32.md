# v0.32 — Solve-to-verification, not a fixed-attempt benchmark

## Actual outcome: an independently hidden-verified historical repair

**A real free-model-authored fix for youtube-dl #43 (`url_basename`) passed
the original upstream public regression and Nykra's separate pinned-Docker
hidden verifier.** No human-authored replacement function, upstream gold
implementation, or hidden-test content was supplied to the model.

The important finding is not an adaptive-policy win. The first live
continuation was **blocked after 32 successful model completions by a free
provider HTTP 429 rate limit**. Twenty-nine of those new replies contained a
sole function but had standard-library `import` statements placed above it;
the original function-only validator rejected all 29 before running Docker.
The frozen model outputs were later safely normalized and regraded.

| Evidence | Result |
| --- | --- |
| Original live history including v0.31 prefix | 32 distinct real provider completions, then HTTP 429 |
| Original strict validation | No accepted public or hidden-verified repair |
| First chronological recoverable output | **Attempt 11** |
| Attempt 11 normalized public / hidden | **Pass / Pass** |
| Independently regraded attempt 29 public / hidden | **Pass / Pass** |
| Additional inference used by both recovered checks | **0 calls** |
| Chronological public Docker runs, attempts 4–11 | **4** |
| Repeated failed public results reused, attempts 4–11 | **4** |
| All new verification Docker work in both recovery experiments | 5 public + 2 hidden runs |
| Actual provider-reported tokens for original 32 completions | 24,202, reported $0 |
| Original provider-reported tokens through attempt 11 | 6,835 |

In the chronological experiment, the source from attempts 4, 5, 9 and 11
underwent real restricted Docker testing; attempts 6, 7, 8 and 10 reused
the prior exact failing result. The **first candidate that passed both
independent public and hidden tests was the model's attempt 11**, generated
well before the 429 limit. A separate confirmation of attempt 29 also passed
both suites independently. This demonstrates the normalizer is not accepting
source on a superficial syntax check alone.

The difference between 32 calls observed and the 11th attempt as a potential
stop point (**21 calls and 17,367 provider-reported tokens**) is
**counterfactual, not realized live cost reduction**. The original live
trial did make 32 calls and hit the rate limit; replay of those *already
completed* calls shows it could have stopped when attempt 11's valid source
was properly handled. We make **no claim of a real executed 21-call saving**.

## Reproducibility and provenance

A protocol was frozen before any v0.32 model inference:

- [Frozen issue and public-example protocol](evidence/v32_solve_until_verified_protocol.json).
  SHA-256 `06c611da5df7b48143409e1bd477707eacd834c17b21ecf82ce81e8b87b64502`.
  The task was previously studied by Nykra, not an unseen or blind issue.
- [Original free-model provider output history](evidence/v32_solved/youtube-dl-43_baseline_depth.json).
  Each source, SHA-256, exact provider response ID, usage, original public
  result, and 429 infrastructure failure is retained unchanged.
- [Chronological safe-import normalization replay](evidence/v32_solved/youtube-dl-43_chronological_import_replay.json),
  executed with `python -m scripts.replay_import_normalizer_v32 --approve`,
  without any new model requests; refuses to overwrite original evidence.
- [Independent successful attempt-29 grading](evidence/v32_solved/youtube-dl-43_import_normalization_regrade.json)
  and [aggregate reconciliation](evidence/v32_solved/v32_recovery_summary.json).
- Source adapter: `nykra/model_source_normalizer.py`; reproducible
  solve-to-verification runner: `scripts/solve_until_verified_v32.py`.

The adapter parses the model output as Python source; it only accepts a single
named function preceded by a finite allowlist of **stdlib import-only**
statements. It copies those imports into that function and preserves the
original AST body and docstring. It never synthesizes new repair logic. It
still rejects multiple functions, arbitrary top-level execution, disallowed
imports, bad Python syntax and modified function signatures. The historical
grading code then executes the resulting function only in the pinned,
restricted Docker evaluator. The exact original and normalized SHA-256
identities are recorded.

The updated solve-to-verification runner now applies this safe normalizer on
future completed model outputs **before** the original signature and public
grading checks. Its stop rule is passing independent hidden verification,
not an arbitrary three- or four-attempt budget. Provider rate limits,
infrastructure failures and operator interruptions remain genuine blockers;
the local checkpoint allows later examination without inventing successes.

## What this proves — and what it does not

**Proven:** A source-validation/assembly improvement recovered a real
model-generated upstream bug repair that the strict agent workflow discarded,
and hidden tests confirmed it. Reusing repeated failed public grading in
the replay also reduced actual Docker work.

**Not proven:** Improved reasoning by the language model, improved adaptive
search decisions, better performance across other libraries, or a reliable
rate of resource savings. The other previously unsolved historical issue,
tqdm #1, was not continued under v0.32 because the free provider returned
HTTP 429. Nykra's independent optimized arm was also not completed under
the same provider conditions. **Do not publish this as a fair completed
baseline-versus-adaptive accuracy comparison.**

The approach can be improved by testing more unseen issues with equal
provider budgets and an agreed deterministic import-normalization
preflight in *both* arms before the first real model call. That will
separate improvements from the source adapter versus effects caused by
adaptive exploration. This task did not change any upstream Git checkout,
and no code was promoted, committed or pushed.
