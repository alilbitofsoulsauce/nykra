# Real upstream issue repair: controlled Codex pilot

## Scope and provenance

On October 11, 2026, Nykra ran a *small exploratory comparison* on real historical bugs from the published [BugsInPy project](https://github.com/soarsmu/BugsInPy), using original [youtube-dl](https://github.com/ytdl-org/youtube-dl) buggy Git commits and regression tests taken from the corresponding upstream fixes. These were **not** synthetic regressions introduced by Nykra.

The [four-task frozen protocol](evidence/v17_external_pilot_protocol.json) (SHA-256 `495453711ee9d89b2a5d0e640eef6feed9b2f472f4926b062ca101f4f9e07658`) was written before any model candidate was generated. Each eligible task underwent a reproduction gate: the recorded buggy revision must fail the official regression test while the upstream reference-function fix passes in the same Docker grading environment.

The model is authenticated official Codex CLI 0.160.0 using `gpt-6-luna` (low reasoning effort). Both arms share the model, first prompt, one-function patch interface, public test feedback, four-attempt maximum and 70-second model-call limit. Task arm order is counterbalanced. Baseline is a depth/parent revision policy; the Nykra arm uses the *actual* `select_next` adaptive ancestry logic with branch resets after stagnation. There is no model training or self-modification.

## Results

| Historical task | Baseline | Nykra adaptive | Outcome |
| --- | --- | --- | --- |
| BugsInPy 1 — `_match_one` | **0/4** attempts passed | **0/4** passed | Neither repaired the official regression; Nykra reset branch on attempt 4 |
| BugsInPy 10 — `js_to_json` | Not run | Not run | Prevalidation exclusion: buggy test timed out under the frozen 40-second limit; reference fix passed |
| BugsInPy 11 — `str_to_int` | **1/1** passed | **1/1** passed | Both repaired the official regression on their first attempt; ceiling |
| BugsInPy 13 — `urljoin` | **0/4** passed | **0/4** passed | Neither repaired the regression; Nykra reset branch on attempt 4 |

**Primary task-level result among three eligible paired tasks:** baseline **1/3**, Nykra **1/3**. Nykra-only wins **0**, baseline-only wins **0**; the exact one-sided paired discordance p-value is **1.0** because there were no discordant outcomes. A confidence interval from three tasks would be uninformative.

Among eligible tasks, both arms completed **9 model turns** with no model-call errors. The model reported **97,423** tokens and **96.96 seconds** summed model-call time for baseline, versus **91,508** tokens and **104.24 seconds** for Nykra. These are descriptive counters, **not** demonstrated efficiency improvements. Nykra did select a new independent root on the fourth attempt for two failing tasks; the baseline continued revising. That is evidence the branch-policy integration changes actual Codex execution, **not** evidence that its decisions improved success.

Raw outcomes: [task 1](evidence/v17_youtube_dl_bugsinpy_1.json), [task 10 exclusion](evidence/v17_youtube_dl_bugsinpy_10.json), [task 11](evidence/v17_youtube_dl_bugsinpy_11.json), [task 13](evidence/v17_youtube_dl_bugsinpy_13.json), and the [machine-readable issue-level summary](evidence/v17_external_pilot_summary.json). They include model-generated candidate source and source hashes, actual parent ancestry, Docker grader outcomes, prevalidation results, attempts, tokens and durations. Never replace existing raw results.

## Docker grading controls

For each evaluation, Nykra exported the exact buggy upstream commit and inserted only the recorded upstream regression test file (not the source-code fix) into a disposable build context. A generated Dockerfile built an image from digest-pinned `python:3.8.20-slim-bullseye` using `COPY` only, with no `RUN` or network in the build. The grading run used its immutable image ID; network disabled, read-only root, UID 65534, all capabilities dropped, no-new-privileges, 384 MB memory limit, one CPU, 64 PID limit, no host mounts, ephemeral temporary storage, and a 40-second timeout. Source was never executed on the Windows host.

This is risk-reducing constrained execution, **not a certified adversarial sandbox**. The Windows Docker daemon remains trusted. No arbitrary internet-sourced setup scripts were run. Authenticated model credentials were never mounted into evaluator containers.

## Limits and next rigorous test

- **The same official regression test was public feedback and the final success criterion. No independent hidden test set was used.** Passing one regression does not establish a correct full issue fix or freedom from other regressions.
- Four historical tasks, all from one project, are much too few to estimate general effectiveness. Only three completed matched comparisons.
- Historical bug fixes and issue descriptions may appear in the model's training data; contamination was not ruled out.
- Candidate output was restricted to replacing one existing top-level function rather than normal multi-file repository repair.
- The 40-second timeout exclusion on issue 10 is retained as a registered result; do not silently omit it when counting enrolled tasks.
- One official regression test can produce all-zero public scores. The next study should freeze richer public feedback and *separately held-out* regression suites before any model generation.
- This is **not an official SWE-bench or BugsInPy leaderboard score**. No general coding-agent improvement, cost reduction, transfer across agents or recursive self-improvement has been established.

The next meaningful experiment should use a broader, preregistered, independently testable task set; validate buggy and gold environments before model calls; provide fair structured public failures to both arms; use a separately hidden final evaluator; keep equal attempt, token and time budgets; and count task-level successes including exclusions, invalid patches and timeouts.

## Reproduction

From the Nykra root, with the BugsInPy metadata and upstream source checkouts under the ignored `experiments/` directory, Docker ready and the previously authenticated Codex runner:

```powershell
python -m unittest discover -s tests -p "test_real_issue*.py" -v
python -m nykra benchmark preflight
```

Use `nykra.real_issue_trial.run_task(task_id, output_path, approve=True)` with a **new output path** to repeat model inference. Existing frozen outcome files are intentionally not overwritable. The pure `nykra.real_issue_report.summarize(require_complete=True)` recomputes headline metrics without re-running models.
