# Real Codex Luna coding experiment — Nykra v0.33–v0.35

## Actual outcomes

Native Codex CLI version 0.151, signed in using the workstation's existing ChatGPT authentication, successfully ran GPT-5.6 Luna (the lowest-cost GPT-5.6 model offered to this account). GPT-5.4 mini and GPT-5.1 Codex mini were rejected as unsupported for Codex ChatGPT authentication. Usage is counted under the ChatGPT plan; published API prices are not evidence of actual money billed.

The v33 and v34 protocols were frozen before new Codex completions. Three previously studied historical upstream issues had three existing genuine failed attempts, and Nykra's actual controller selected a different action at the fork: baseline revised the last attempt, adaptive began a new root.

| Actual historical task | Baseline Codex completions | Adaptive completions | Actual independent public and hidden verification |
| --- | ---: | ---: | --- |
| tqdm #1, tenumerate start index | 1 | 1 | Both pass |
| youtube-dl #43, URL basename | 1 | 1 | Both pass |
| youtube-dl #3, malformed HTML entities | 1 | 1 | Both pass |
| **Total** | **3** | **3** | **3/3 vs 3/3** |

CLI-reported input tokens for the three paired tasks: baseline **43,836**, adaptive **43,583** (including cached input). CLI-reported output tokens: baseline **803**, adaptive **1,225**. Both arms each performed three real public Docker grades and three separate hidden-verification sessions. The adaptive policy made different decisions but showed **NO accuracy, inference-call or evaluator-work advantage** in this cohort. A stronger model resolved these tasks on the first new proposal.

## Harder issue and feedback-driven recovery

The Nykra adaptive arm then attempted the previously studied youtube-dl #5 timestamp parser. Ten actual Luna completions produced ten public-test failures. Examination revealed the historical v20 grader recorded only pass/fail and output hashes, suppressing the actual upstream public assertion. Regrading the previously failed candidate in restricted, offline, pinned Docker with a new public-feedback adapter exposed:

    AssertionError: 1455428700 != 1455471900

The error differed by 43,200 seconds (12 hours). The v35 feedback intervention was frozen before NEW rescue completions. Nykra continued with this public diagnostic and the same model; the first subsequent completion failed publicly, while the **second passed BOTH the upstream public regression and separate hidden verifier**. An additional standalone check using the original frozen historical v20 grader again returned **public PASS and hidden PASS**. The winning model-authored source has SHA-256:

    43dae3bfa836c64e438c4da310d58cd7c45d7fab27f5d9fa067fb144a6890182

Hard-task real usage: **10 failed Luna calls before actionable feedback + 2 Luna calls after the intervention = 12 calls to actual verified solution**. Rescue-phase usage was 30,422 reported input and 1,745 output tokens, plus two public Docker grades and one hidden grade, followed by an independent public+hidden retest.

This is real **feedback and workflow recovery**, NOT proof the adaptive policy beats a fair baseline. The intervention was introduced posthoc after observing the stall, and the hard-task baseline was not independently continued with the same diagnostic. All issues were used in earlier Nykra evaluations, so this is not a new blind benchmark.

## Reproducible receipts and code

- docs/evidence/v33_codex_luna_protocol.json and docs/evidence/v34_codex_hard_forks_protocol.json — protocols frozen before paired Codex work
- docs/evidence/v33_codex_luna/ and docs/evidence/v34_codex_hard_forks/ — raw candidate code, actual Codex usage, and real public+hidden grader receipts
- docs/evidence/v35_feedback_rescue_protocol.json — pre-rescue protocol
- docs/evidence/v34_codex_hard_forks/youtube-dl-5_public_diagnostic.json — real sanitized public assertion
- docs/evidence/v35_rescue/youtube-dl-5_nykra_actionable_feedback.json — two real rescue completions and their validation
- docs/evidence/v35_rescue/youtube-dl-5_independent_recheck.json — independent final confirmation
- docs/evidence/v35_codex_luna_results.json — checked aggregate metrics
- scripts/run_codex_luna_v33.py, scripts/run_codex_hard_forks_v34.py, scripts/rescue_codex_v35.py, nykra/v35_public_feedback.py — implementation

No generated source was executed on the Windows host or promoted into the upstream projects. No Git commit or push was performed. The next genuinely decisive study requires unused tasks, same rich public feedback across both arms, repeated matched policy forks, and measured terminal success and cost.
