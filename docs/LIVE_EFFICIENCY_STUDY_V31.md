# v0.31 development — Real independent multi-issue free-model efficiency study

## Finding

**No coding success or inference-token uplift. An actual reduction in public
Docker work was reproduced on historical upstream issues.**

Three pre-registered historical BugsInPy defects across **youtube-dl** and
**tqdm** were evaluated by two independently sampled live inference arms:
ordinary depth search and depth search with Nykra's v0.30 exact-request cache,
v0.29 duplicate-public-evaluation reuse, and v0.30 repeat-failure halt enabled.

| Measured outcome | Baseline depth | Nykra optimized depth |
| --- | ---: | ---: |
| Hidden-verified real issues solved | **1 / 3** | **1 / 3** |
| Independent provider/model calls | **8** | **8** |
| Provider-reported total tokens | **3,498** | **3,499** |
| Actual public Docker evaluations | **8** | **6** |
| Public Docker evaluations reused | **0** | **2** |
| Hidden Docker grading sessions | **1** | **1** |
| Exact inference request cache hits | **0** | **0** |
| Early-stop interventions | **0** | **0** |
| Model-reported provider cost | **$0** | **$0** |

Measured public Docker evaluator calls decreased by **2/8 (25%)** at unchanged
task results. This is the principal positive result. There was **no model-call
reduction, no token reduction, no accuracy uplift**, and no exercised early
halt. The optimized arm consumed one more provider-reported token.

The real inference and public Docker evaluations for all 3 issues completed,
with actual Docker hidden checks for the selected passing attempts. Nykra
never sent hidden cases or diagnostics to the model. Free route only,
`cohere/north-mini-code:free`, reasoning disabled, model fallbacks disabled,
max 1,500 output tokens and 90 seconds per model call. All actual model calls
returned reported cost $0; that does not guarantee future provider pricing,
unlimited quota, or model performance.

## Results by historic issue

| Issue | Baseline model / public Docker | Optimized model / public Docker | Hidden verified |
| --- | --- | --- | --- |
| youtube-dl #28, invalid HTML entities | 2 / 2 | 2 / 2 | **Both pass** |
| tqdm #1, `tenumerate(start)` | 3 / 3 | 3 / **2** | Neither passes |
| youtube-dl #43, URL basename extraction | 3 / 3 | 3 / **2** | Neither passes |

For **tqdm #1**, both arms' third candidates matched their own second
failed source. Nykra reused the earlier public-test verdict and skipped
one restricted Docker grading invocation. For **youtube-dl #43**, the
optimized arm's third candidate matched its *first* failed source, so
Nykra reused that nonconsecutive receipt. The optional early-stop guard
does not fire for nonconsecutive duplicates; the second candidates were
different from the first. For **youtube-dl #28**, both arms produced a
different second repair that passed the public and hidden suites; neither
optimization changed the work. The arms were sampled independently: provider
response IDs differ even when the output content is byte-identical.

## Frozen design and task provenance

The [SHA-256-frozen study protocol](evidence/v31_live_study_protocol.json)
was written **before** any v0.31 model calls. Its SHA-256 is
`d50af1b42f21ebf0361a315d37fe822abe992bd5a32d88dac32cc6461f951f24`.

The real upstream buggy/fixed commits, source target function, evaluator
protocol hashes and fixed-commit regression test paths were registered in
advance. All three were reused from Nykra's earlier v0.20/v0.21 studies,
where frozen reference preflights demonstrated a buggy public/hidden failure
and a reference public/hidden pass. These issues are **not novel to Nykra**.
The benchmark reuses official historical Git source and the existing
pinned restricted Docker graders rather than trusting model-authored tests.

Both arms had the exact same *initial prompt hash* on each issue and
independent authenticated free-model completions. On a failed public
attempt, both arms received the same type of bounded actionable public
diagnostic and prior generated function; no hidden oracle or fixed source was
exposed. Both used **depth**, a three-model-call-per-issue limit,
and the same source validation, test suite and grader. Task execution order
alternated baseline-first / optimized-first / baseline-first. Repeated
completions and failed attempts remain in the raw archive; none were
discarded. The full result includes SHA-256 of each source proposal, original
model text, provider response ID, reported token usage, public grader receipt,
and (after both arms finish) selected hidden verdict.

Optimization handling in the v0.31 supervised study adapter:
- An exact repeated model request may be satisfied by Nykra's
  `generate_cached` adapter in an operator-private per-task/arm namespace.
  **It wasn't triggered:** every live revision prompt differed.
- A public-test failure for the exact same generated function source within
  an arm is reused from the original actual Docker receipt; a reused result
  is labeled and never counts as a new Docker execution.
- The guard imports Nykra's actual
  `multifile_workflow._repeated_public_failure` predicate and would
  suppress the next model request after *two consecutive identical failed
  proposals*. **No such two-proposal sequence occurred** in the optimized
  arms before their final calls, so no observed inference-call saving
  should be credited.

Note that the v0.31 adapter is **one-function replacement** and uses the
earlier v0.20/v0.21 pinned graders; it is not a v0.31 native multi-file
Git-diff or autonomous third-party agent integration. No untrusted generated
source was executed directly on the Windows workstation.

## Independent evidence, reconstruction, and exclusions

Original [youtube-dl #28](evidence/v31_live_issues/youtube-dl-28.json),
[tqdm #1](evidence/v31_live_issues/tqdm-1.json), and
[youtube-dl #43](evidence/v31_live_issues/youtube-dl-43.json) raw
model-generated Python, public diagnostics, hash-linked receipts,
and terminal hidden grading are archived.

[Reconciled aggregate machine result](evidence/v31_live_efficiency_summary.json)
is independently reconstructed by
`python -m scripts.summarize_live_efficiency_v31`
(which refuses to overwrite the existing frozen result) or by importing
`summarize()`. It verifies:
- Frozen protocol digest and per-task source/grade provenance.
- No repeated provider response IDs across the arms; each arm owns real,
  independently returned live completions.
- Exact first-prompt hashes across both arms per task.
- Complete reported token values and provider-reported zero cost for all
  completions.
- Only authenticated, exact same-source previously failed public verdicts
  qualify as cached, and baseline never used public caching.
- Selected hidden grading only after public passing and only after both
  arms have generated their model outputs.
- Actual evaluations and saved evaluations reconcile to original receipts;
  model budgets stay at or below three per issue per arm.

Run the offline receipt integrity tests:
~~~sh
python -m unittest discover -s tests -p test_v31_efficiency_study.py -v
~~~

To run *one new* approved study task on a workstation with compatible
historical source checkouts, pinned local Docker images, and an environment
injected `OPENROUTER_API_KEY`:
~~~sh
python -m scripts.run_live_efficiency_v31 --task-index 0 \
  --cache-root /private/nykra-v31-cache \
  --output-dir /new/experiment/results --approve
~~~
The output is checkpointed after each model completion and cannot overwrite a
prior run. The script reads the SHA-frozen v0.31 task cohort, requires
explicit approval, and never invokes a non-`:free` model.

## Interpretation and next gate

This is genuine, modest **agent work efficiency**, not improvement in
coding intelligence. The change saved two repeated public Docker tests out
of eight. At a three-issue sample, a confidence interval around the saved
fraction would be extremely unstable, and runs share one model/provider,
historical code and prior evaluations. A free model can deterministically
generate identical outputs even for different prompts; the study cannot
attribute that to Nykra. The interventions did not improve task pass rate,
inference tokens or model calls. They may be less helpful when proposals are
unique; early stopping can reduce the chance of a later repair.

A more meaningful next gate would use **previously unused issues across more
repositories**, multiple independent random draws per issue, a fixed equal
paid-or-free provider budget, and true agent-native multi-file diffs. Record
behavior with the early-stop rule actually triggered and measure the
success/work tradeoff, rather than assuming reducing calls is always good.

The v0.31 experiment is an uncommitted development feature. No source was
promoted, and no Git commit or push was performed.
