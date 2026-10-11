# Nykra v0.13 — First Real Model-Authored Coding Study

**Executed October 11, 2026 on the authorized Rel.AI-connected Windows workstation.**

## Research question

Does Nykra-guided feedback improve an actual coding model's performance on newly written Python algorithm challenges compared with that model's initial unassisted attempt?

**Finding:** This study **cannot estimate an improvement**. ChatGPT authored a valid initial implementation for each of the eight challenges, and each implementation passed **all 18 training tests and all 40 held-out tests**. Nykra's policy correctly stopped without requesting revisions. There was **no assisted second candidate** to compare. This is a measured **ceiling effect**, not a successful proof of Nykra's general effectiveness.

## Real execution protocol

The model in this conversation authored eight complete `solve(...)` functions. Those initial candidate sources were saved as one immutable manifest before executing the tests. Existing `nykra.relai_agent.RelaiAgent` sessions (using the authorized Rel.AI MCP tool) were created with `depth` policy, a maximum of two candidates and a fixed runtime cap per problem. Candidate source was evaluated by Nykra's restricted Python worker in real subprocesses. The worker receives only Python source and test inputs; expected answers are computed by separate reference functions in the host.

Training and held-out input sets are deterministically generated using different seeds. Tests now assert **no duplicate held-out inputs and no overlapping input arguments across the training/held-out split**. An integrity-test failure initially detected shared handpicked edge cases; those cases and duplicate filtering were fixed **before final evidence was published**. Eight deliberately incorrect controls, which are NOT presented as model-generated baseline attempts, are independently rejected by the scoring worker on both splits.

The model's code was evaluated on algorithmic tasks, not preexisting repository bug reports. The model was in the same conversation as the evaluation implementation, so **the test descriptions, reference algorithms and potential cases are not externally blinded**. This evaluation is useful for instrumenting an actual model-through-Rel.AI workflow but is not a contamination-resistant benchmark. All tools ran with active user permission; no cloud coding-agent usage was billed by Nykra.

## Actual outcome

| Model-authored task | Initial training | Initial held-out | Revisions needed |
| --- | ---: | ---: | ---: |
| Longest substring with unique characters | 18/18 | 40/40 | 0 |
| Maximum contiguous subarray sum | 18/18 | 40/40 | 0 |
| Shortest substring covering required multiset | 18/18 | 40/40 | 0 |
| Maximum non-overlapping half-open intervals | 18/18 | 40/40 | 0 |
| Total rainwater trapped | 18/18 | 40/40 | 0 |
| Next strictly greater value to the right | 18/18 | 40/40 | 0 |
| Longest common string prefix | 18/18 | 40/40 | 0 |
| Number of distinct subsequences | 18/18 | 40/40 | 0 |
| **Total** | **144/144** | **320/320** | **0** |

**Actual model first-pass success: 8/8 = 100%. Measured assisted uplift: zero observed, not causally estimable.**

The eight tasks are not equivalent to 320 independent coding challenges. The 320 held-out cases are correlated within eight problem families. Neither a statistically meaningful policy win nor a statistically meaningful general no-effect conclusion is justified.

## Reproduce this evaluation

The exact model-authored candidate source manifest is preserved as `docs/evidence/v13_model_authored_first_attempts.json`; machine-readable scores and source hashes are preserved as `docs/evidence/v13_coding_study_results.json`.

Execute from the Nykra checkout:

```powershell
python -m nykra coding-study --candidates-file docs/evidence/v13_model_authored_first_attempts.json --approve
python -m unittest discover -s tests -p test_coding_study.py -v
```

The CLI evaluates real Python subprocesses on deterministic training and held-out inputs and reports exact per-task outcomes without changing the live Nykra observation database.

## Related prior model improvement, not causal evidence

In the earlier v0.11 interactive Rel.AI session, the same connected ChatGPT model started with an imperfect bracket checker (14/18 training cases), received Nykra training feedback, revised its code, and passed 18/18 training and 32/32 held-out cases. That is a real observed feedback-driven repair, but **it involved more candidate attempts than the initial solution**, and there was no independent equal-budget no-Nykra control. It therefore cannot be presented as the size of Nykra's causal effect.

A separate v0.12 deterministic grid-search study measured a strong benefit of a known Manhattan-heuristic search policy, but **that task family uses no LLM** and should never be combined with this coding-agent result.

## Unattended model-runner status

- **Rel.AI:** verified supervised connected ChatGPT execution, observer healthy. Rel.AI itself is not a callable independent model backend.
- **OpenCode:** CLI and an authentication record detected, but the free-model synthetic tool-disabled inference request timed out in more than one attempt. A separate verified error/result is still required before enabling headless generation; no paid-provider fallback was performed.
- **Codex:** official non-interactive SDK and CLI interfaces are documented but no authenticated Codex runtime has been tested on this workstation, and no native Nykra adapter has been validated.

References: [Codex SDK](https://github.com/openai/codex/blob/main/sdk/typescript/README.md), [SWE-bench Verified benchmark](https://www.swebench.com/verified), and OpenAI's [2026 evaluation limitations and contamination analysis](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/). These references motivate independent repository tasks and blind evaluation; Nykra does not currently implement the official SWE-bench harness.

## Necessary next experiment

Use an authenticated, supported, explicit-model runner for at least 30 previously unseen repository issue-fixing tasks in disposable sandboxed checkouts. Assign identical task budgets to a no-Nykra control and a Nykra-assisted arm, randomize order, and prohibit giving the model held-out tests or reference fixes. Count every failure, timeout, total tokens, wall time, evaluated patches and test regressions. Use predeclared primary success criteria and paired or blocked uncertainty estimates. If the baseline solves every task, increase difficulty without silently altering an already registered experiment.

**Verdict:** Nykra's coding evaluation, feedback, persistence and integrity checking work for real model-authored programs. This v0.13 study **does not establish** that Nykra improves model reliability, reduces token costs or makes coding agents more autonomous. It establishes the need for a harder, independently controlled model-runner trial.
