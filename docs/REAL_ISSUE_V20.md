# Nykra v0.20 — Independent historical-issue replication

## Research question

Does Nykra's deterministic independent-root exploration decision improve real coding-agent patch success over a depth/revision baseline on **previously unused upstream defects**, when both strategies inherit the exact same failing model-generated history and receive repeated model continuation samples?

**Observed answer in this small study: no improvement demonstrated.** The comparison is stronger than v0.19 in task novelty and repeated inference calls, but is still not a general performance evaluation or official BugsInPy/SWE-bench benchmark score.

## Previously unused task cohort and eligibility

Four historical real defects selected from the published [BugsInPy](https://github.com/soarsmu/BugsInPy) metadata, with pinned original upstream commits. **None of these issue IDs had appeared in earlier Nykra v0.17–v0.19 evaluation runs.** Three came from youtube-dl, and the fourth from the separately cloned tqdm repository. Historical patches could still be present in a model's pretraining data; "new to Nykra" is not equivalent to uncontaminated.

The frozen, amended [four-task protocol](evidence/v20_protocol.json), SHA-256 `9eec931522e43e5c3afadeaa592e0a9cbd1b1c7c7639153ad7219b6ad731c2ab`, identifies exact buggy/fixed Git commits, target top-level function, distinct public and hidden checks, arm order, Docker image ID and inference budgets.

**Pre-inference amendment:** Initial reference prevalidation revealed (a) an incorrectly chosen hidden RFC timezone expectation on youtube-dl 5 that even the historical reference fix did not satisfy, and (b) a missing historical `nose` dependency in tqdm's old pytest suite. **Before any v0.20 Codex repair calls**, the mistaken hidden oracle was corrected to a UTC/GMT case and `nose==1.3.7` was added to a locally verified, digest-pinned Python 3.8/pytest image. Both [original protocol](evidence/v20_protocol_initial.json), [initial hidden specification](evidence/v20_hidden_spec_initial.py), and [original failed reference preflight](evidence/v20_prevalidation_initial.json) were preserved. The [amended reference preflight](evidence/v20_prevalidation.json) confirmed all four tasks eligible.

For **every task**, the original buggy commit failed both the public regression and withheld behavioral checks, while the official upstream fixed-function source passed both. The isolated evaluator never executed original upstream setup scripts on Windows. It used constrained disposable Docker images and networkless, nonroot, read-only-root test runs with capability, CPU, memory, PID and time limits. These are risk reductions, **not a certified malicious-code isolation boundary**.

## Controlled experiment

- Same authenticated `gpt-6-luna` Codex runner (low reasoning effort), same project issue, function prompt, original buggy function and public pass/fail grade.
- One shared, independently generated/evaluated **three-attempt maximum** prefix per task. If a shared attempt passed publicly, there was no experimental fork.
- On exactly three *valid publicly failed* attempts, the real agent-independent policy engine must disagree at action four: **baseline revises attempt 3**, Nykra **starts a new root**. If a model yields invalid syntax or infrastructure failure, stop without making up a branch.
- For each genuine fork, independently generate **two fourth-action samples for each arm**, repeating exactly the same policy-specific prompt and shared ancestry. Later draws never receive prior draw results. Four post-fork model calls per forked task.
- **Only after all samples were produced** does the grader test publicly passing candidates against separate hidden behavioral/upstream cases. Hidden outcomes never feed another model call.
- Same maximum 70-second per-call limit and a **soft** 25,000 model-reported-token threshold per draw. There was no hard API-enforced per-call token ceiling. Record actual usage and any overshoot.

A sample is a stochastic Codex call; multiple draws from a task are **not independent real task instances**. This study deliberately holds the decision point fixed, rather than making serial two-attempt repairs as in v0.19.

## Complete results

| Original task | Shared attempt outcome | Baseline continuation | Nykra continuation |
| --- | --- | --- | --- |
| youtube-dl bug **3**, `unescapeHTML` | 3 public failures, real policy fork | **0/2** public passes | **0/2** public passes |
| youtube-dl bug **5**, `unified_timestamp` | 3 public failures, real policy fork | **0/2** public passes | **0/2** public passes |
| youtube-dl bug **23**, `js_to_json` | First generated function had invalid Python syntax | Not run | Not run |
| tqdm bug **1**, `tenumerate` | First shared candidate passed public and post-inference hidden tests | Not run | Not run |

**Registered and prevalidated:** 4/4. **Actual policy forks:** 2/4 issues. **Independent continuation draws on genuine forks:** baseline 4, Nykra 4. **Full hidden-verified continuation repairs:** **0/4 baseline versus 0/4 Nykra**. Neither arm produced a publicly passing continuation on these forked issues.

One *shared* tqdm candidate was repaired and later passed its independent hidden checks; that is evidence the inference+grader workflow still records a valid upstream repair, but it confers **no success advantage on either policy**. One youtube-dl task exited without a fork because the model's candidate had `SyntaxError`; this was an invalid-model-patch event, **not** a failure of the Docker reference environment. It remains counted in the registered cohort.

**Model-reported post-fork tokens** totaled **6,395 baseline** versus **18,854 Nykra** across four calls each. A single Nykra root generation on bug 3 contributed much of that difference. These figures are descriptive, not a statistically reliable cost estimate; they also exclude the identical shared-prefix costs. No draw exceeded the 25,000-token soft ceiling; all draw counters were reported.

Raw evidence: [bug 3](evidence/v20_youtube_dl_3.json), [bug 5](evidence/v20_youtube_dl_5.json), [bug 23](evidence/v20_youtube_dl_23.json), [tqdm bug 1](evidence/v20_tqdm_1.json), [post-inference shared repair hidden audit](evidence/v20_shared_prefix_hidden.json) and [machine-readable summary](evidence/v20_summary.json). These retain actual model source, hashes, model results, public/hidden grades, frozen protocol provenance, attempt ancestry, tokens and durations.

## Interpretation and next move

The previously observed **Nykra-only PySnooper success in v0.19 did not generalize** into any successful fourth-action repair on the new v0.20 defects. This result is **null**, not evidence that Nykra can never help; it argues against publishing broad, unqualified "Nykra improves coding agents" claims now.

The natural cohort has just two real forkable issue instances, with two correlated samples per arm. The two forks had zero successes in either group, so an exact paired sign test has **zero discordant issues and no informative p-value**. Avoid aggregating individual draws as independent successes, joining these results with the earlier reused tasks as though they were newly sampled, or treating historical benchmark patches as uncontaminated.

Further rigorous research should enlarge the *previously unused* task population; use more repositories and independent restricted evaluators; distinguish invalid candidate syntax from environment failure; provide richer common public feedback (not merely pass/fail); repeat stochastic samples under actual equal enforced token budgets where supported; and prefer complete multi-file patch benchmarks. Compare both task-wide success and success **conditional on a true fork**, while documenting the very high early-success and model-invalid rates.

## Release and workstation status

This is research implementation in the local `nykra` source tree, **not** a new installed/released version. All v0.17–v0.19 results remain unchanged. Nothing was committed or pushed.
