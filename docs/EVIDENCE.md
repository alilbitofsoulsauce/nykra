# Nykra Evidence Ledger

**Last reviewed: October 11, 2026.** This is the durable record of observed outcomes, not a marketing summary. Future README edits should carry the same numerator, denominator, task type, comparator, provenance and limitations. Keep original raw evidence under `docs/evidence/`; retain null results and failures.

## A. Reference-search policy comparison — positive on maze tasks

- Protocol and raw evidence: [benchmark methods](BENCHMARK_RESULTS.md), [machine-readable run](evidence/grid_paired_seed20261011.json).
- Workload: **48 matched, procedurally generated solvable 5×5 mazes**, executed by a deterministic reference subprocess worker; **not a language model or software-repair agent**.
- Equal expansion cap: **12** candidate expansions per arm on each task, same evaluator.
- Breadth-first baseline: **19/48 = 39.58%** solved; mean **10.50** expansions.
- Goal-distance-guided adaptive search: **48/48 = 100.00%** solved; mean **5.17** expansions.
- Difference **+60.42 percentage points**, paired bootstrap 95% interval **+45.83 to +72.92 percentage points**; one-sided exact paired p = **1.862645149230957e-09**. These statistics are conditional on this particular maze distribution and favorable Manhattan heuristic.
- Claim supported: a specified informed search policy improves these particular constrained reference-search tasks. **Not supported:** general coding-agent gain, learned exploration policy or recursive self-improvement.
- **Independent procedural seed follow-up (20261012)**: Another 48 tasks, equal 12-expansion cap; breadth-first **22/48 (45.83%)**, adaptive **47/48 (97.92%)**; mean expansions **10.17 vs 4.98**; paired difference **+52.08 points**, bootstrap 95% interval **+37.50 to +66.67 points**, one-sided exact paired p **2.9802322387695312e-08**. One task was unsolved in both arms; zero execution failures. [Raw seed-20261012 evidence](evidence/grid_paired_seed20261012.json). This is another draw from the **same favorable generator**, not independent real-world tasks or a separate algorithm family.

## B. Connected ChatGPT–Rel.AI feedback repair — observed correction, uncontrolled

- Protocol and session observations: [Rel.AI-first integration](RELAI_AUTOPILOT.md).
- Workload: **one balanced-brackets Python implementation** authored in the connected ChatGPT turn and executed through Rel.AI/Nykra.
- Measured progression: initial implementation passed **14/18** training cases; feedback-guided model revision passed **18/18** training cases and **32/32** separately evaluated held-out cases.
- Two real candidate programs executed; Nykra requested the revision and finalized the best scored candidate.
- Claim supported: the connected workflow can identify a defect and facilitate an effective revision. **Not supported:** any causal advantage over the same model with an equal time/candidate budget and no Nykra, because no such independent control ran.

## C. Model-authored first-attempt coding study — ceiling effect; zero measured uplift

- Protocol and raw evidence: [full study](REAL_CODING_STUDY.md), [frozen first-attempt code](evidence/v13_model_authored_first_attempts.json), [task-by-task scores and hashes](evidence/v13_coding_study_results.json).
- Workload: **8 Python algorithm challenges**, each with one genuine model-authored candidate frozen *before test feedback*, executed through ChatGPT–Rel.AI–Nykra.
- First attempts: **8/8 fully correct**; training **144/144**, held-out **320/320**.
- Separate held-out input sets have **zero overlap** with training arguments, and deliberately incorrect non-model controls are rejected by the evaluator.
- Measured Nykra-assisted revisions **0**, measured additional successes **0**: the unassisted first attempts already passed, so there was no opportunity to improve them in this study.
- Claim supported: the real model-generated first attempts, evaluator and audit workflow function correctly on these small tasks. **Not supported:** Nykra's general benefit or lack of benefit to Codex, Claude Code, Cursor or large-repository repairs. The tasks and evaluator are not externally blind.

## D. Unattended native model runner and repository-repair control

**Historical installation status before the later successful Codex direct-release recovery:** See the [machine-readable runner setup/probe failures](evidence/native_runner_probes_2026-10-11.json) for all attempts, elapsed time where available, and whether an actual inference response was obtained. Rel.AI is a working execution/observation harness and model-authored revisions work inside an active connected ChatGPT turn. Rel.AI itself does not expose a verified independent model-completion endpoint. Detecting provider credentials or an executable is not equivalent to successful authenticated inference.

- An isolated OpenCode free-model smoke request previously timed out; it was **not** counted as a successful model call.
- In the October 11 follow-up, the workstation contained a ChatGPT-authenticated Codex configuration, but the separately isolated official npm installation timed out; its remaining native Windows binary failed to start with **WinError 193**. No successful Codex inference or controlled repository-repair result exists from that attempt. A subsequent offline Windows package retry did not leave a usable native executable, and the independently tried official checksum-validating standalone installer also timed out before any executable was installed. **That earlier installation attempt produced no authenticated native inference.** The later official direct-download Codex runner did succeed, separately documented in section E; do not present the failed npm attempt as successful.
- Do **not** claim SWE-bench Pro scores: the official benchmark requires independently graded patches in isolated environment images, and Nykra has not run it.
- Do **not** upgrade a version or report statistically significant model benefit solely from these diagnostics.

### External methods and adapter sources

- [Official Codex TypeScript SDK](https://github.com/openai/codex/blob/main/sdk/typescript/README.md) — noninteractive SDK turns, streamed events, resumable agent threads.
- [Official Codex iterative repair guide](https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex) — JSON outputs, revision and independent verification.
- [Official SWE-bench Pro V2 evaluation protocol](https://github.com/scaleapi/SWE-bench_Pro-os/blob/main/v2/README.md) — isolated tasks and independent patch replay, task budget accounting. These references guide a *future* benchmark; they are not results achieved by Nykra.

## E. Verified native Codex paired repair pilot (v0.14)

**Full report:** [Native Codex Pilot](NATIVE_CODEX_PILOT.md). The official Codex Windows v0.160.0 release was downloaded directly, hash-verified against its GitHub release digest, and ran a real ChatGPT-authenticated GPT-6 Luna noninteractive inference turn. It remains an isolated optional runner orchestrated through Rel.AI, not an installed universal Nykra driver.

- **Four predeclared, small function-level Python bug repairs**, 14 public and 32 disjoint hidden cases each; same model and a maximum of two attempts per task and arm.
- **Original v1:** baseline **1/4** tasks solved, Nykra-guided **1/4**; the strict AST source interface prevented second attempts after initial invalid output, so v1 is mainly an integration diagnostic. [v1 evidence](evidence/v14_native_codex_v1_summary.json).
- **Separately documented post-hoc v2:** same four tasks and model, with equal AST/test feedback and retry opportunities. Baseline **1/4 solved, 32/128 hidden cases passed**, Nykra-guided **1/4 solved, 37/128 hidden cases passed**. The five additional hidden passes occurred on a still-unsolved CSV task. Each arm used seven model attempts. [V2 evidence](evidence/v14_native_codex_v2_summary.json) and [frozen follow-up protocol](evidence/v14_codex_pilot_protocol_v2.json).
- **Verdict:** Verified headless model inference and instrumented evaluation. **No evidence of higher fully solved task count**, no externally blinded repository repairs, and no statistical claim from four tasks. The Nykra-guided arm changes the second-attempt revision *prompt*, not model weights or the full history-driven Nykra search policy.

## F. First Git repository-source patch study (v0.15)

A separate frozen [six-task protocol](evidence/v15_repo_pilot_protocol.json) injected predefined regressions into **genuine Nykra Python modules** in isolated Git copies. The exact [v0.15 report](REPOSITORY_REPAIR_PILOT.md), [task-level results](evidence/v15_repo_repair_summary.json), and six original full candidate sources/patch diffs are retained. Authenticated Codex GPT-6 Luna ran in read-only inference mode; the host applied only a typed target-function replacement to each disposable Git checkout. Both baseline and guided strategies fixed **6/6 tasks and 156/156 hidden checks** with **one model turn per task**, despite equal two-turn maximums. **No Nykra revision guidance was ever activated.** Both arms tied; the difference was exactly zero tasks and zero hidden checks. These were *artificially injected bugs in real repository modules*, not actual independent GitHub issues, and Python patch execution was not run within a hardened container. No general coding-agent effect or recursive self-improvement was demonstrated.

## G. Shared exploration-policy implementation and real Codex smoke (v0.16)

The shared [exploration-policy and external-evaluation architecture](EXTERNAL_EVALUATION.md) delegates breadth/depth/adaptive branch decisions to one validated source, now used by both the durable Rel.AI agent loop and trusted Git-repair model runner. In one authorized read-only Codex GPT-6 Luna inference run, the adaptive-policy executor repaired a known injected p-value regression **on its first attempt**, passing **26/26 held-out checks**. [Exact model output and scores](evidence/v16_real_codex_policy_smoke.json). This is an engineering smoke test, **not a baseline comparison or evidence that branching helps**. Automated tests independently exercise actual parent choice and stagnation-root selection using intentionally scripted candidates; do not label those scripted tests as model benchmark victories.

The original external evaluation preflight found Docker/Podman absent and WSL unavailable. **After installation and reboot on October 11**, Docker 29.8.2 with its Linux daemon and WSL2 became responsive; a digest-pinned BusyBox image passed Nykra's built-in offline, nonroot, read-only, network-disabled, resource-limited [fixed-command container smoke](evidence/docker_smoke_2026-10-11.json). Five new mocked smoke tests passed, alongside the prior 153-unit regression suite. This demonstrates execution controls on a benign script, **not** protection against arbitrary hostile code. Untrusted external repository evaluation remains blocked by the fail-closed gate; no SWE-bench or independent GitHub issue outcomes were produced.

## H. Real upstream issue repair (v0.17)

[Four preregistered historical BugsInPy youtube-dl issues](REAL_ISSUE_PILOT.md) were assessed with a digest-pinned, nonroot, offline Docker evaluator and an authenticated Codex model. Of four registered tasks, three passed the eligibility check. The fourth (bug 10) had a buggy-test timeout and was excluded **before model calls** under the frozen rule. The three completed paired tasks gave **1/3 upstream regression passes for both baseline depth and Nykra adaptive**; zero discordant outcomes. Nykra selected independent new-root attempts on two failing issues, showing real policy operation but no success gain. [Frozen protocol](evidence/v17_external_pilot_protocol.json), [raw results](evidence/v17_external_pilot_summary.json), [bug 1](evidence/v17_youtube_dl_bugsinpy_1.json), [bug 10](evidence/v17_youtube_dl_bugsinpy_10.json), [bug 11](evidence/v17_youtube_dl_bugsinpy_11.json), [bug 13](evidence/v17_youtube_dl_bugsinpy_13.json).

**Limitations:** same public regression used for feedback and final grade, no independent hidden tests; possible historical contamination, one repository and only three eligible task pairs. This is **not** a valid general coding-agent effectiveness claim or official SWE-bench score.

## I. Cross-repository real repairs with withheld final tests (v0.18)

The [next frozen pilot](REAL_ISSUE_V18.md) used three new historical youtube-dl issues and one original PySnooper issue from BugsInPy, with genuinely separate hidden behavioral checks and additional upstream regression tests. **All four** issues passed the eligibility gate before model generation. In matched Codex comparisons, baseline depth solved **2/4**, Nykra adaptive solved **2/4**, with one Nykra-only successful held-out repair and one baseline-only successful held-out repair. There were zero observed exploration decision divergences at the three-attempt cap, so task-level differences cannot be attributed to the adaptive policy. [Frozen protocol](evidence/v18_protocol.json), [pre-inference environment amendment](evidence/v18_protocol_preflight_original.json), [raw report](evidence/v18_summary.json), and the original per-task outcome files are retained.

The correct conclusion remains **no demonstrated causal or general coding-agent effectiveness improvement**. This is an exploratory, small historical-issue study with one-function patches, possible benchmark contamination, a non-certified Docker security boundary and a soft model-reported token budget—not official SWE-bench or a BugsInPy leaderboard score.

## J. Genuine shared-prefix policy fork (v0.19)

[Full v0.19 report](REAL_ISSUE_V19.md). Natural re-use of all four v0.18 historical issues generated **a single shared prefix per task**, then evaluated it once. Three tasks were publicly solved within three model turns (later **3/3 passed separate hidden grading**) and therefore correctly had **no policy fork**. PySnooper bug 3 reached three common failed candidates, and the real exploration engine selected **baseline: revise last** against **Nykra: independent new root**. Nykra's continuation passed public and hidden tests; baseline did not. Only **one** naturally forkable issue exists in this sample.

A distinct **failure-conditioned archival replay** followed a separately frozen rule: three original v0.18 tasks had documented three-failure histories; all nine failures were revalidated in the current Docker grader. Both arms used the exact same histories, diverged at action four, and received matched incremental call budgets. Results: **Nykra 3/3** held-out repairs versus **baseline 2/3**, with one Nykra-only success on PySnooper. The PySnooper bug overlaps with the natural cohort and these **must not be pooled as independent tasks**. Each cohort's exact two-sided sign p-value is **1.0**; the sample is statistically inconclusive.

[Original natural protocol](evidence/v19_protocol.json), [stalled-history conditional protocol](evidence/v19_stalled_protocol.json), [post-model shared-prefix hidden audit](evidence/v19_shared_prefix_hidden.json), [machine summary](evidence/v19_summary.json), and immutable per-task evidence are retained. **Supported:** the real Codex policy branch can diverge from the same actual evaluated history and can sometimes produce a correct repair. **Not supported:** population causal advantage, broad agent improvement, representative success rates, independent replication across fresh tasks, or hardened untrusted-code execution.

## K. Previously unused cross-project real issue replication (v0.20)

The [v0.20 controlled experiment](REAL_ISSUE_V20.md) selected **four BugsInPy defects never before tested by Nykra**, across youtube-dl and a newly downloaded tqdm Git repository. All original buggy revisions failed separate public and hidden regressions; all reference fixes passed both after a fully preserved **pre-inference oracle/dependency amendment**. Each task received exactly one shared generated/evaluated prefix. Two tasks had **three failed attempts and a genuine baseline-revise versus Nykra-new-root decision fork**. Repeated **two independent fourth-action samples per policy** yielded **zero successful repairs in either arm: baseline 0/4 and Nykra 0/4 calls** across the two tasks. A tqdm task succeeded in the shared prefix and passed post-inference hidden checks; a fourth task stopped on invalid generated Python syntax without forcing a fake fork. Post-fork model-reported tokens were 6,395 baseline vs 18,854 Nykra (descriptive only).

[Amended registered protocol](evidence/v20_protocol.json), [initial preserved protocol](evidence/v20_protocol_initial.json), [preflight including all reference outcomes](evidence/v20_prevalidation.json), [raw machine summary](evidence/v20_summary.json) and individual task sources/results are saved. **Outcome:** no replicated coding-agent task-success uplift, no strong statistical effect estimate, and no justification for a broad Nykra performance claim. The prior v0.19 PySnooper-specific benefit did not reproduce on these new issues.

## L. Actionable public-only failure diagnostics (v0.21)

The [v0.21 study](REAL_ISSUE_V21.md) adds a reusable function/AST validator, distinct model-invalid versus evaluator failure classifications, and a printable path-scrubbed **900-character maximum** public test diagnostic. Six untouched historical youtube-dl bug IDs were preregistered; five were eligible after fully preserved pre-inference reference-only test-oracle corrections; one was excluded. Three first common Codex candidates were already publicly and hidden verified and thus **not paired wins**. On two valid one-call revision pairs from identical initial candidates, **bare status-only feedback solved 0/2, actionable public feedback solved 1/2**, with a real hidden-verified fix on `url_basename` bug 43. The other paired task failed in both arms.

[Amended protocol](evidence/v21_protocol.json), [original pre-inference protocol](evidence/v21_protocol_initial.json), [all reference outcomes](evidence/v21_prevalidation.json), [original failed reference gate](evidence/v21_prevalidation_initial.json), [complete raw machine summary](evidence/v21_summary.json) and each original model candidate/grade are preserved. **Interpretation:** one task-level enriched-feedback advantage, paired exact two-sided p=1.0 (one discordant issue), small n, historical contamination and stochasticity; **no proven general effectiveness gain and no demonstration of Nykra policy superiority**.

## M. Rel.AI-hosted portable upstream Git coding workflow (v0.22)

[Integration instructions](AGENT_WORKFLOW_V22.md). A portable session-level `workflow start/next/submit/finalize` API takes code from any authorized connected agent without importing its vendor SDK. Rel.AI is the tested supervisory execution host; authenticated Codex read-only inference supplies optional model-generated proposals. The host validates an AST function contract, applies the candidate as an **actual Git patch in a disposable copy of the real upstream source**, records patch/source hashes, evaluates the public regression under the locked constrained Docker checker, follows the shared vendor-neutral exploration policy, and runs independent hidden checks only at terminal finalization. No original user repository is modified.

The frozen [v0.22 engineering protocol](evidence/v22_workflow_protocol.json) intentionally reuses two previously benchmarked youtube-dl issues. Eight distinct Codex completions yielded 14 genuinely applied/tested patch instances across two paired depth/adaptive workflows; bug 43 was solved at a shared third attempt (**both policies pass hidden**), while bug 27 generated an actual decision fork, revise versus new root, and **both policies failed**. Thus each policy achieved **1/2** task successes; **no benefit demonstrated**. A separate complete CLI subprocess lifecycle using the upstream fixed source passed public and hidden checks but is explicitly classified as a **reference control**, not model success.

[Audited machine summary](evidence/v22_workflow_summary.json), [the paired bug 27 result](evidence/v22_workflow_pair_youtube_dl_27.json), [the paired bug 43 result](evidence/v22_workflow_pair_youtube_dl_43.json), [CLI control](evidence/v22_cli_reference_smoke.json) and [portable per-session Git patch/source evidence index](evidence/v22_session_export_index.json). This establishes an end-to-end **narrow function-repair integration**, not unrestricted autonomous multi-file editing, universal native agents, or model-policy uplift.

## N. Verified identical-result Git/Docker reuse (v0.23)

[Full v0.23 measured engineering report](WORK_SAVINGS_V23.md). Implemented a new `workflow reuse --session TARGET --verified-session SOURCE --approve` method that can transfer a verified, actually Git-applied public-regression receipt to another **exactly matching** authorized agent branch without new model, Git or public Docker calls. The source task, pinned evaluator, history, parent/action, prompt/source/patch hashes and pinned upstream source SHA must match; infrastructure failures and replay chains are refused. Both branches still receive independent terminal hidden checks.

A pre-frozen two-issue replay of original v0.22 **real upstream model-generated patch sources** compared ordinary two-branch evaluation with shared receipt evaluation using the same Docker grader and zero additional model inference. Real public Docker and actual Git apply calls dropped **14→8** (6 avoided, **42.9%**). Combined observed wall time fell from **121.9779s to 70.6527s** (51.3252s, **42.1%**). Both original real issue success/failure results were preserved (bug 43 passed both policies; bug 27 failed both). Order was counterbalanced, but elapsed measurements still depend on machine conditions. No proven correctness improvement, new-model token reduction, or universal speedup.

[Immutable protocol](evidence/v23_reuse_protocol.json), [source-verified machine summary](evidence/v23_reuse_summary.json), [bug 27 record](evidence/v23_reuse_youtube_dl_27.json), [bug 43 record](evidence/v23_reuse_youtube_dl_43.json), [portable SHA session registry](evidence/v23_session_export_index.json), and [independent Rel.AI CLI source reference control](evidence/v23_cli_reuse_control.json). The provider-neutral `nykra/v23_paired.py` accepts a ChatGPT/Rel.AI proposal callback and does not invoke Codex or any model itself.

## O. Independent-session persistent public Git/Docker result cache (v0.24)

[Detailed v0.24 implementation and metrics](CONTENT_CACHE_V24.md). Added opt-in `workflow submit --cache-public`. The content-addressed receipt key includes exact source, upstream original and patched Git code, original/fixed upstream commits, public regression test source, evaluator implementation and protocol fingerprints, and pinned Docker base image ID. Separate agent policies, feedback settings and histories can reuse **identical public evaluator inputs** without rerunning Git apply or public Docker tests. Hidden tests are never cached; each publicly passing candidate still undergoes its independent terminal hidden Docker verification. Local cache receipt tampering, mismatched source, evaluator changes, unavailable pinned Docker and infrastructure failures fail closed. This remains a **trusted-local-host** cache, not a cryptographically hostile-user-proof database.

Two historically reused real upstream `youtube-dl` model-authored candidate sources were preregistered and replayed **without any new model inference**, in 12 independent agent-session runs across counterbalanced cold and warm conditions. Baseline **6** real public Docker tests and Git applications versus cache **2** (4 avoided, **66.7% less duplicate execution**). Observed wall time **69.7810s versus 32.6652s**, saving **37.1158s (53.2%)** in the two local trials. Issue 27 failed every condition and issue 43 passed independent hidden checks 3/3 in each condition. These results establish exact-input work elimination, **not** increased model correctness or reduced model-token usage, and elapsed gains do not generalize automatically.

[Frozen input protocol](evidence/v24_protocol.json), [machine summary](evidence/v24_summary.json), [bug 27](evidence/v24_cache_youtube_dl_27.json), [bug 43](evidence/v24_cache_youtube_dl_43.json), [twelve portable source/patch session records](evidence/v24_session_export_index.json), [two original public receipts](evidence/v24_public_receipt_index.json), and [full CLI subprocess independent-session control](evidence/v24_cli_independent_control.json).

## P. Multi-file transactional patch engine (v0.25)

[Engineering implementation, threat boundary and reproduction](MULTIFILE_TRANSACTION.md). Added an agent-provider-neutral CLI and API for approved multi-file Git diffs in a clean, committed repo. The engine enforces exact file allowlists and path restrictions, tests a Git-applied patch inside a disposable checkout, and can promote the exact tested file bytes with best-effort rollback. A seeded synthetic fixture requires two interacting Python-module fixes. The [pinned offline Docker trial](evidence/v25_multifile_docker_trial.json) records two modified files and passing test exit code 0. Negative cases cover unauthorized paths, symlinks, wrong patches, creation/removal, failing tests, CLI approval and promotion failures. **This is an engineering safety capability, not a new real upstream bug or a coding-agent performance comparison.**

## Next rigorous experiment

A convincing coding-agent efficacy estimate needs a **same-model, equal-budget** no-Nykra baseline and Nykra-guided arm on diverse, previously unseen repository issues. The agent must not access the hidden verifier or reference solutions. Preserve run IDs, candidate patches, token/cost/time budgets, failures, test regressions and exact task manifests. Include confidence intervals based on tasks, not individual correlated test cases. If the baseline solves all tasks, explicitly record the ceiling effect and predeclare a harder *new* task set instead of cherry-picking failures.

## Verify the evidence links and immutable data

Run `python -m unittest discover -s tests -p test_evidence_registry.py -v` from the Nykra repository. This verifies the SHA-256 hashes of source evidence files, the headline numeric claims against the stored JSON results, and the README's evidence links. It does **not** independently reproduce historical model calls or turn the old experiments into statistically valid agent controls.

## Evidence retention rules

1. Update the README with plain-language outcomes and the source links above, including negative results. Do not duplicate only the most favorable metrics.
2. Save raw or reproducible per-task outcomes and immutable candidate-source digests. A documented correction must explain what changed and why.
3. Distinguish deterministic reference workers, supervised model-authored code and authenticated unattended model runners.
4. Never count intentionally wrong evaluator controls as model-authored baseline failures.
5. No Git commit, remote push, released package, or published benchmark claims without the user's explicit instructions.
