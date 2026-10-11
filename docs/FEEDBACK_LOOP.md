# Nykra v0.10 — Iterative AI Coding Feedback

Nykra v0.10 supports **sequential, feedback-driven coding exploration** through the existing ChatGPT-to-Rel.AI MCP connection. Unlike the v0.9 prewritten proposal pools, the connected AI agent supplies each candidate *after* seeing the previous training result and Nykra's requested exploration branch.

This works without fixing the unrelated agyc installation, registering another MCP tool, or obtaining a new model API key. Nykra does **not** run its own LLM: the connected model still has to participate in each proposal and revision.

## Workflow

```powershell
python -m nykra iterate start --task balanced-brackets --policy depth --budget 3 --max-seconds 1200 --approve
```

Save the returned session ID. Nykra responds with `request.kind = new_root` or `request.kind = revise`, including the relevant evaluated parent attempt ID. The model authors a single Python `solve` function in a file it controls. It can submit that candidate through the authorized Rel.AI execution tool:

```powershell
python -m nykra iterate submit --session SESSION_ID --candidate-file proposal.py --approve
```

Nykra validates the source, executes it in the bounded Python evaluation worker, and returns training score, passed/total count, and up to three failing examples showing **input, expected result, and observed result**. The session is preserved in a separate local SQLite store.

For each subsequent request, the model must write a genuinely revised or newly rooted proposal. Repeating the same test without changing the code does not constitute learning. The model can check current progress and resume after losing connection using:

```powershell
python -m nykra iterate next --session SESSION_ID
```

When a candidate meets the passing threshold, the attempt limit is reached, or the host decides to stop, supply the **exact code of the highest-scoring evaluated candidate**:

```powershell
python -m nykra iterate finish --session SESSION_ID --candidate-file best.py --approve
```

The final action verifies that the file's content hash matches Nykra's recorded best attempt and runs **held-out tests** that were not exposed in training feedback. The final score is available only after this step; it is never used to select intermediate candidates.

If the session must be abandoned:

```powershell
python -m nykra iterate abort --session SESSION_ID --approve
```

Abandoning a prospective-trial session counts as a failed assignment; Nykra does not hide unfinished or failed work when estimating policy success.

## Policy behavior

- **Breadth:** Requests a second independent root before asking the agent to revise earlier roots, then prefers shallower, less-explored candidate ancestry.
- **Depth:** Requests a revision of the most recently evaluated candidate and continues that branch.
- **Adaptive:** Requests revision of the highest-scoring evaluated candidate; after repeated stagnation it can request a fresh root.

These are **policies for requested exploration structure**, not modifications to the model's private reasoning. Parent IDs record Nykra's requested ancestry; they cannot prove that the model truly edited the exact parent source rather than writing unrelated code.

## Optional prospective assignment

To use a prespecified randomized study, create a trial with evaluator `nykra-coding-fixtures-v1`, objective `maximize`, and a fixed attempt/time budget and threshold. Then supply `--trial TRIAL_ID --task-key UNIQUE_TASK_KEY` to `iterate start` with the **identical** `--budget`, `--max-seconds` and `--threshold`.

A prospective session uses the randomly assigned arm regardless of the command's default policy. Its assignment is claimed before any model-authored candidate is executed, and `iterate finish` submits the final held-out score to the prospective report. A session that exceeds its total elapsed wall time receives a timeout violation rather than a passing result.

**A prospective comparison needs independent tasks and adequate assigned samples in both arms.** Repeated sessions on the same three publicly visible coding fixtures are not a statistically credible benchmark of general coding agents.

## Observed live integration

On October 11, 2026, ChatGPT used Rel.AI to run a new balanced-brackets session:

| Step | Observed result |
|---|---|
| Initial model-authored implementation | 10/18 training tests (55.6%) |
| Nykra feedback | Incorrectly accepted `([)]` and other invalid bracket sequences |
| Model-authored revision | 18/18 training tests (100%) |
| Explicit final evaluation | 32/32 held-out tests (100%) |

Nykra recorded two scored, linked attempts in local history without saving the candidate source code. The session was explicitly finalized. **This demonstrates an actual model-in-the-loop feedback correction on one small problem, not autonomous model self-improvement or a causal policy win.**

## Privacy, restrictions, and failure modes

The session store contains IDs, score metrics, policy, file content digest, and a small number of **synthetic public training examples**. Source code, prompts, raw model output, secret test cases and candidate file paths are not persisted by Nykra's iterative session engine. The **external caller's candidate source files remain on disk** until explicitly deleted; a SHA-256 digest is a pseudonymous fingerprint, not encryption.

Python AST restrictions, timeouts, isolated interpreter flags and temporary directories reduce mistakes but are **not a hardened sandbox** suitable for arbitrary adversarial code. Only allow trusted, supervised candidates. Nykra's total time budget includes time waiting for a model response; use realistic per-task limits when working across turns.

The two Nykra SQLite stores (evaluated attempts and session metadata) are separate for backward compatibility. A power loss during the narrow interval between recording an attempt and its session step can leave a history event that is not listed in the session; manual review may be necessary. Nykra does not promise transactional exactly-once semantics across those two databases.

The current installed Rel.AI application's internal model or planning controller is unchanged. Truly unattended candidate generation will require an authorized model runner/API and independent tasks with reproducible, isolated evaluator environments.
