# Nykra v0.12 — Measured Exploration Benchmark

**Status:** Reproducible *reference-search* experiment, completed October 11, 2026. This is actual local candidate expansion with independent path validation, **not** an LLM coding-agent benchmark.

## Fixed specification

- Protocol: `grid-paired-prospective-v1` implemented in `nykra/benchmarks.py`.
- Seed: `20261011`; 48 unique, randomly generated **solvable** 5×5 grid mazes, with random starts, goals and three wall-density levels.
- Generator independently verifies solvability with a BFS oracle before accepting a task; this oracle **does not reveal a path to either tested agent**.
- Reference agent: `nykra/reference_agent.py`, a separate Python subprocess proposing legal neighbor states. Neither policy calls an LLM.
- Baseline: breadth-first traversal. Challenger: Nykra adaptive search, prioritizing the worker's Manhattan distance-to-goal heuristic.
- Both algorithms independently process **the identical set of 48 tasks** with a maximum of **12 candidate expansions per task** and equal 12-second wall-time limits. Failed executions would count as unsuccessful.
- Independent evaluator: `nykra.agent_host.evaluate_grid` (verifies every move and that the final path reaches the goal).
- Primary outcome: success rate by task; secondary: actual expansions used. Analysis: **paired** exact one-sided discordance/binomial test and paired task bootstrap interval. No other model capabilities differ between arms.

## Observed results

| Metric | Breadth-first baseline | Nykra adaptive |
| --- | ---: | ---: |
| Completed tasks | 48 | 48 |
| Successful solutions | **19** | **48** |
| Success rate | **39.58%** | **100.00%** |
| Average candidate expansions | **10.50** | **5.17** |
| Execution failures | 0 | 0 |

Matched result breakdown: 19 tasks solved by both, 29 solved only by adaptive, 0 solved only by breadth-first, 0 unsolved by both.

- Success-rate difference: **+60.42 percentage points** for adaptive.
- Paired bootstrap 95% interval for the difference: **+45.83 to +72.92 percentage points** (conditional on this generator and resampling scheme).
- Exact one-sided paired p-value: **1.862645149230957e-09** (29 improvements, zero regressions). This is **not zero**.
- Task manifest SHA-256: `2f6cdba57845285c6770dc06831dd47cd532a1a3dfd48c0cafe7ebc7ebf32b03`.

The machine-readable evidence is committed to the *working tree* as `docs/evidence/grid_paired_seed20261011.json` (not a Git commit). This report was produced by running the benchmark **twice with the same specified seed and budget**, and the generator manifest was independently recomputed. Candidate paths were computed at runtime, not replayed.

Reproduce it on a Python-enabled workstation from the Nykra root:

```powershell
python -m nykra benchmark paired-grid --tasks 48 --budget 12 --seed 20261011 --approve
```

## Additional seed replication — October 11, 2026

Using the same frozen reference worker, independent verifier, 12-expansion limit and 48-task count, a second run used **seed 20261012** to generate a different set of solvable mazes.

| Metric | Breadth-first | Adaptive |
| --- | ---: | ---: |
| Task successes | **22/48** | **47/48** |
| Success rate | **45.83%** | **97.92%** |
| Average expansions | **10.167** | **4.979** |
| Execution failures | 0 | 0 |

- Paired success difference: **+52.083 percentage points**.
- Paired bootstrap 95% interval: **+37.5 to +66.67 points** (generator conditional).
- One-sided exact paired p: **2.9802322387695312e-08**.
- Match breakdown: both solve 22; adaptive only 25; breadth-first only 0; neither solve 1.
- Manifest SHA-256: `65957b3464bbc73a2bf54d1f94938831034893908456a647e5e9f72a8e33b0f5`.
- [Raw execution result](evidence/grid_paired_seed20261012.json).

This repeated positive result is **additional evidence of informed search on the same generator**, not an independent coding-agent study, proof of learning or evidence that real agent workflows improve. The heuristic and expansion cap continue to favor goal-directed search.

## What this genuinely proves

Under this predefined reference workload and fixed expansion cap, the goal-directed adaptive frontier found valid paths more reliably and with fewer expansions than breadth-first traversal. **Nykra's policy selection can improve controlled algorithmic search under constrained budgets.** It also establishes that the benchmarking harness can run equal-budget paired comparisons with independently verified outcomes and explicit failure accounting.

## What this does *not* prove

- **Not Codex, Claude Code, Cursor or a ChatGPT performance result.** The worker is a deterministic search program and the tasks are small mazes, not software development.
- The adaptive policy is given a goal-directed Manhattan heuristic; this benchmark is intrinsically favorable to that kind of informed search, particularly with only 12 expansions. A generic exploration intelligence engine will not automatically produce that useful heuristic for arbitrary tasks.
- The task generator filters out unsolvable mazes. Conclusions apply to this restricted class, not arbitrary, adversarial or unknown tasks.
- This is a single reference benchmark distribution and a single fixed seed; other seeds and distributions might yield different improvements. Tasks from a procedural generator are not necessarily representative of independent real-world coding workloads.
- The exact statistical test is a descriptive within-generator paired test; it doesn't eliminate benchmark selection effects, model/data leakage, or multiple-testing concerns from wider research.
- The benchmark **does not show Nykra learning or updating its policy from previous task outcomes**. It demonstrates a *fixed policy's* benefit on this search class, not recursive self-improvement.

## Before a claim about improved real coding agents

1. Integrate a working authorized Codex SDK or another native model runner into the shared `AgentDriver` contract, without routing everything through Rel.AI.
2. Register a broad set of held-out coding tasks with independent real tests; prevent prompt and solution leakage.
3. Randomize comparable tasks between the same model with Nykra policy enabled/disabled. Match model, prompts, cost, tokens, tools, task order, candidate limits and retries.
4. Retain failures, timeouts, resource costs, evaluation logs and task-revision parent links.
5. Replicate on a second agent and on new tasks before advertising general improvement.

**Research conclusion:** The reference benchmark provides positive, meaningful **algorithmic-search evidence**. It does not yet meet the bar for general coding-agent effectiveness or recursive self-improvement.
