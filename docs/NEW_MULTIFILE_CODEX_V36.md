# v0.36 — First previously unused two-production-file Codex task

## Result: independently confirmed repairs, Nykra policy was less efficient

This is Nykra's first new historical, multi-production-source, matched
Codex Luna repair study from this development series. The target was upstream
BugsInPy **youtube-dl bug #35**, a real Arte upload-date defect requiring
coherent behavior in both `youtube_dl/extractor/arte.py` and
`youtube_dl/utils.py`.

The original buggy Git commit and official fixed revision were pinned.
A registered upstream public method and a separately authored, previously
frozen five-case hidden test suite ran in restricted pinned offline Docker.
The hidden tests exercised extractor JSON behavior (including direct
shooting-date preference and older VDA fallback) as well as date parsing.

**Preflight before any v0.36 live model proposal:**

| Original Git source | Public upstream regression | Five independent hidden checks |
| --- | --- | --- |
| Real buggy revision | **FAIL** | **FAIL** |
| Official reference-fixed revision | **PASS** | **PASS** |

Both arms then independently sampled real ChatGPT-authenticated Codex
**GPT-5.6 Luna** completions. Both were supplied the same first prompt,
buggy code context, task statement, exact two-file allowlist, frozen public
test assertions, provider settings and public-only feedback. Neither saw
the official reference implementation or hidden tests.

| Measured outcome | Baseline depth | Nykra adaptive |
| --- | ---: | ---: |
| Real Codex completions to verified success | **4** | **7** |
| First three attempts | Invalid Git patch | Invalid Git patch |
| Attempt 4 controller action | Revise last patch | Independent new root |
| Invalid/non-applicable Git diffs | **3** | **6** |
| Real public Docker evaluations | **1** | **1** |
| Original separate hidden Docker verification | **PASS** | **PASS** |
| Extra independently repeated public + hidden Docker check | **PASS / PASS** | **PASS / PASS** |
| Provider-reported input tokens (includes cached input) | **64,000** | **203,922** |
| Provider-reported output tokens | **2,578** | **6,214** |
| Sum of CLI-reported model request wall seconds | **55.941** | **159.13** |
| Independent agent patches each modify both production files | **Yes** | **Yes** |

**Nykra took three more new model calls, 139,922 more reported input tokens,
3,636 more output tokens and about 103.2 more model-wall seconds.** Both
agents solved the task, but baseline was more efficient. Under this
single-task run, the proposed adaptive reroot is **not advantageous**.

Invalid patches count as failed model attempts (even though no public Docker
code was executed) and remain fully present in the immutable raw attempts.
Every actual public/hidden Docker grader session is separately counted. The
winning patches had two original production-file Git-diff sections each, were
strictly checked against the allowlist, applied successfully, and passed
both test suites, including independent later regrading.

## Protocol and evidence

- `docs/evidence/v36_multifile_protocol.json`: real upstream bug IDs,
  exact Git SHAs and file allowlists; same first prompt and policy controls.
  SHA-256:
  `b7532405c50fcdd077a00d4fd6a295cdeb5aa275095da4a9ea0af13925aaaad4`.
- `docs/evidence/v36_hidden_arte_dates.py`: evaluator-owned five-case
  hidden suite, frozen before inference, with SHA
  `a53ffe6f1fa582cf1e1d53e429b2eb2c787e4a1f9680331e85bf41f4ab44e3cb`.
- `docs/evidence/v36_multifile_preflight.json`: all four genuine
  buggy/fixed public/hidden Docker source checks (eligible).
- `docs/evidence/v36_multifile_live/youtube-dl-35_baseline_depth.json`
  and `youtube-dl-35_nykra_adaptive.json`: entire separate model text,
  Git diffs, prompt SHA-256, receipts, usage, public test statuses, hidden
  success and decisions.
- `docs/evidence/v36_multifile_independent_regrade.json`: new real
  public and hidden Docker execution of each selected model patch.
- `nykra/v36_multifile_grader.py`: pinned historical repo archive,
  production patch allowlist, real Git application checks and restricted
  Docker-only tests. No source was executed on Windows.
- `scripts/run_unseen_multifile_v36.py`: true Nykra `select_next`
  policy and actual Codex model requests, no arbitrary stop attempt count,
  persistent per-arm checkpoints, no patch promotion.

The hidden suite is separately written but not a third-party independently
blinded official benchmark oracle. The original public case is upstream
BugsInPy; this is not an official SWE-bench score. The issue is historical
and may exist in training data, although it had not appeared in Nykra's prior
task evaluations. A single issue with one sampled comparison cannot
establish general inference/correctness differences.

## Next engineering priority

All ten model proposals across both arms were either **invalid/non-applicable
Git patches** or valid patches that passed both suites immediately. The
limiting factor was *Git patch serialization*, not patch semantics under a
valid candidate. This strongly motivates a separately pre-registered
agent-neutral output adapter that safely produces and validates Git diffs
from bounded structured edits, rather than relying entirely on a model
generating correct hunk counts and context.

To test that intervention fairly, use another previously unused multi-file
issue and enable the same deterministic formatting/assembly preflight in
**both** baseline and Nykra arms. After that, re-test adaptive search on
tasks where valid patches fail substantive public assertions, using fixed
Codex call ceilings only to limit quota and continuing an actual task to
independent hidden verification where resources permit. Do not claim
Nykra improves coding-agent performance based on the present negative result.

This is development evidence, not a release. No Git commit, patch promotion,
push or publication occurred.
