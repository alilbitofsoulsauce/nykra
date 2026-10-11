# Nykra v0.19 — Controlled coding-agent policy fork

## Research question

When an authenticated coding model has made **three identical, evaluated unsuccessful repair attempts**, does the deterministic Nykra exploration policy's **independent-root decision** yield a better final repair than a depth baseline's **revise-latest-parent decision**, under matched incremental continuation budgets?

Nykra v0.18 previously established a reliable, network-disabled Docker evaluator with hidden behavioral and independent upstream checks on real historical BugsInPy issues. However, its three-attempt ceiling caused **zero actual exploration-policy decisions to diverge**. v0.19 isolates the decision at attempt four.

**This is an exploratory policy-mechanism study. It is not an official BugsInPy or SWE-bench run and does not prove an improvement across agents or projects.**

## Frozen protocol and controls

The [natural-prefix protocol](evidence/v19_protocol.json) was frozen before its model calls (SHA-256 `d3a6431e2bb636f4790c38c949de77b69b70b89f1752609de11281caed922dde`). It reuses **all four** genuine previously evaluated v0.18 issues, rather than choosing a favorable subset: youtube-dl defects 17, 20 and 21 and PySnooper defect 3.

For each task:

1. Generate **one shared prefix** of up to three actual Codex source candidates. The host grades each candidate on the same upstream public regression in an isolated Docker image. The first three calls are made **once**, not separately for each arm.
2. If public validation passes before attempt four, stop and report a shared solution with **no policy fork**. If a model call or Docker run fails, mark the prefix unusable, rather than converting that failure into a policy win.
3. Only when **all three** model-generated candidates fail the public regression does the frozen exploration engine compute both actions. The depth baseline must choose `revise(attempt-3)`; adaptive Nykra must choose `new_root`. If the two actions do not genuinely differ, abort.
4. Both arms inherit the **identical serialized candidate ancestry and public feedback**, with a maximum of two *additional* model calls, 70 seconds per call, 130 cumulative model seconds per arm, and a 35,000 **soft reported-token** ceiling per arm. The selected parent source differs by the policy's actual decision. No hard API token ceiling is claimed.
5. Grade each arm's selected publicly passing patch **once** on the pre-existing v0.18 hidden behavioral/upstream suite. Hidden verdicts never appear in Codex prompts.

Both arms use the same authenticated `gpt-6-luna` low-reasoning-effort executor, original buggy source, single-top-level-function replacement interface, fixed issue wording and a fail-closed, constrained Docker evaluator. Stochastic model generation **after** the fork remains uncontrolled; task outcomes cannot be attributed deterministically to the branch decision from a single draw.

## Natural-prefix cohort: four registered tasks

| Historical issue | Shared prefix | Baseline continuation | Nykra continuation | Interpretation |
| --- | --- | --- | --- | --- |
| youtube-dl bug 17 | Public success at attempt **1** | Not run | Not run | No fork |
| youtube-dl bug 20 | Public success at attempt **3** | Not run | Not run | No fork |
| youtube-dl bug 21 | Public success at attempt **2** | Not run | Not run | No fork |
| PySnooper bug 3 | **Three** public failures | **Fail**, two calls | **Pass public + hidden**, one call | Genuine Nykra-only fork success |

The natural task outcomes are [bug 17](evidence/v19_youtube_dl_17.json), [bug 20](evidence/v19_youtube_dl_20.json), [bug 21](evidence/v19_youtube_dl_21.json) and [PySnooper](evidence/v19_pysnooper_3.json).

The three shared public successes were subsequently tested, **only after all model calls finished**, against the held-out checker. **All three passed**. Their separate [post-inference hidden audit](evidence/v19_shared_prefix_hidden.json) was never returned to the model; the results are shared prefix repairs, not wins for either arm.

**Natural-fork task-level result:** one forkable task; **Nykra 1/1**, **baseline 0/1**, a single Nykra-only win. The exact two-sided paired sign p-value is **1.0**. The other three tasks cannot contribute to a policy-fork effect estimate because the shared prefix already solved them.

## Separate failure-conditioned historical-prefix replication

After the natural-prefix cohort, a second study was explicitly frozen *before new continuation inference*. Its [conditional protocol](evidence/v19_stalled_protocol.json) (SHA-256 `fbe1c8537856ad1bab7e3be441e2518666cb9dc41a53f1a3896181eb4ed3c5d1`) applies a deterministic selection rule to the original v0.18 evidence: include each task where the first eligible recorded arm contains three model-generated, consecutively failing public evaluations with proper depth ancestry. The corresponding prior evidence hashes and candidate hashes were frozen. This yielded **three tasks**; youtube-dl 17 was ineligible.

Every archived candidate was **regraded in the current Docker environment** before branching. All nine rechecks failed as originally recorded. Thus no artificial failures or made-up candidate prefixes were introduced.

| Previously stalled issue | Baseline from identical prefix | Nykra from identical prefix |
| --- | --- | --- |
| youtube-dl bug 20 | **Pass** public + hidden | **Pass** public + hidden |
| youtube-dl bug 21 | **Pass** public + hidden | **Pass** public + hidden |
| PySnooper bug 3 | Fail | **Pass** public + hidden |
| **Full successes (conditional n=3)** | **2/3** | **3/3** |

Evidence: [bug 20](evidence/v19_stalled_yt20.json), [bug 21](evidence/v19_stalled_yt21.json) and [PySnooper](evidence/v19_stalled_pysnooper3.json).

**Conditional paired discordance:** one Nykra-only win, zero baseline-only wins; the two-sided exact p-value is **1.0**. This is a study of **recovery conditional on having already failed three times**, not a representative fresh-task repair rate. Task membership was fixed after viewing v0.18 histories and therefore is **not prospective with respect to those previous failures**.

The PySnooper historical issue overlaps the natural-prefix experiment. **Do not pool the four forks as four independent tasks**, report a combined p-value, or use the repeated PySnooper result as independent cross-project confirmation.

## Causal interpretation and limitations

- **Mechanism demonstrated:** real Codex-generated shared histories were preserved unchanged; the same exploration engine selected `revise` versus `new_root` after three actual failed tests, and the respective continuations were independently graded with hidden cases.
- **Observed task-specific benefit:** Nykra's independent root succeeded on one naturally forkable PySnooper issue where depth failed. The archival replication also favored Nykra on that same issue, while both arms solved the two youtube-dl histories.
- **Not established:** statistical significance, transfer to other models, universal unattended performance improvement, or a general causal success-rate gain. After the controlled decision, the two responses are still stochastic and not seed-matched.
- **Known constraints:** only real but old historically published BugsInPy defects, possible model pretraining exposure, one-function patches rather than unrestricted multi-file repairs, tiny sample, archived-history failure conditioning, a shared issue across cohorts, soft model-reported token limits, and Docker Desktop isolation that is not certified as adversarially secure.

All model candidates, model-call counters, source hashes, public grading outcomes, selected source, final hidden results and decision ancestry are retained in their task JSON records. The [machine-readable aggregate](evidence/v19_summary.json) recomputes the cohorts separately and explicitly declares a pooled effect estimate invalid. The same models or historical task set cannot be treated as independent replication of v0.18.

## Next rigorous experiment

A larger trial should prospectively enrol **previously unused, independently tested real issues** from multiple repositories, include more than one model driver, randomize branch assignment where valid, and obtain repeated stochastic continuation samples **per identical shared prefix**. It should ensure hard API token/time caps where supported, record every failed setup and missing usage counter, and keep hidden final evaluation independent. Compare full-issue patch correctness and total incremental compute, reporting effects conditional on genuine forks separately from general task success.

**Release status:** This is research/evaluator code in the existing Nykra workspace, not an installed v0.19 release. No repository commit, push, or publication was requested or performed.
