# Nykra v0.15 — Git Repository Repair Pilot

**Date:** October 11, 2026. **Primary workstation driver:** Rel.AI. **Model runner:** official Codex CLI 0.160.0 with existing ChatGPT authentication, using GPT-6 Luna at low reasoning effort.

## What was actually tested

This experiment tested **six deliberately injected one-function regressions in genuine Nykra Python modules** copied into fresh disposable Git repositories. This is more representative of repository-source patching than the earlier standalone-function AST worker, but these are **not independently reported real-world issues**, not externally blinded, and not SWE-bench.

The protocol was frozen before model scoring in [v15_repo_pilot_protocol.json](evidence/v15_repo_pilot_protocol.json), with exactly six tasks: p-value tail, maze wall connectivity, bootstrap quantile, finite-score rejection, identifier validation, and truthful driver capabilities.

For each task, the original correct Nykra function was independently shown to pass all seven public and 26 private checks. The injected mutant was shown to fail at least one case in each split. This verification completed before trial execution. The original source never needed repair; every model arm started from its own reproducible defective Git checkout.

## Controls and execution

Both arms used the **same Codex model, model reasoning level, original faulty source, initial prompt, testing oracle, two-turn maximum and 70-second maximum model call**. The six task orders were counterbalanced (three baseline-first, three Nykra-first).

Codex ran **read-only**, with no model tools or direct file-write permissions. Nykra accepted a structured JSON replacement of exactly one named top-level function, applied that replacement to a disposable Git copy and ran ordinary Python against the actual package modules. This removes the previous pilot's artificial ban on standard Python syntax.

After each candidate, the external evaluator ran seven public checks. If they all passed, that arm stopped; otherwise both arms would receive the same public failures and previous proposed code. **Baseline:** regenerate independently; **Nykra-guided:** revise the previous best candidate. Private tests were graded only on the selected final patch. The full source and git diff for every submitted patch are preserved.

A model-supplied Python function is still executed by a timed Python subprocess: this is **not a hardened security sandbox**. The model was not given the independent grader or hidden test inputs in its prompts, but the Nykra project's public source contains its benchmark implementations, so the study is **not externally contamination-resistant or independently blind**.

## Recorded results

| Metric | Baseline | Nykra-guided |
| --- | ---: | ---: |
| Entire tasks fixed | **6/6** | **6/6** |
| Hidden checks passed | **156/156** | **156/156** |
| Model turns used | **6** | **6** |
| Total Codex-reported tokens | **24,323** | **25,357** |
| Sum of model-call wall times | **60.41 s** | **66.88 s** |

All six tasks were solved correctly on the first candidate in **both** arms. **No second-turn strategy was exercised.** The Nykra-guided condition therefore produced **zero additional fully solved tasks** and **zero additional passing hidden test cases**.

The marginal differences in model-reported tokens and elapsed time are not an effect estimate from a representative sample; no cost- or speed-benefit claim is warranted.

**Interpretation:** The host can now obtain authentic Codex model-generated **repository function patches**, safely limit what it edits within disposable Git copies, and independently grade those code changes in normal Python. The **measured Nykra-guidance benefit is zero on these six easy injected regressions**. This finding does not prove a lack of benefit on harder independent repository problems, nor any general benefit.

The full machine-readable [summary](evidence/v15_repo_repair_summary.json) contains task-level results, model usage, final patch hashes and checksums for all six original model outputs:

- [pvalue-tail](evidence/v15_pvalue-tail.json)
- [wall-connectivity](evidence/v15_wall-connectivity.json)
- [bootstrap-quantile](evidence/v15_bootstrap-quantile.json)
- [finite-scores](evidence/v15_finite-scores.json)
- [identifier-validation](evidence/v15_identifier-validation.json)
- [driver-capabilities](evidence/v15_driver-capabilities.json)

## Reproduction without model calls

```powershell
python -m unittest discover -s tests -p test_repository_repair_trial.py -v
python -m unittest discover -s tests -p test_evidence_registry.py -v
python -m nykra doctor
```

The evidence registry cross-checks frozen protocol hashes, per-arm raw patch outputs, task totals and README claims. Running a fresh model experiment requires explicit `--approve`, a working Codex CLI at the tested path, and a **new output filename**; existing evidence is never overwritten.

## Next confirmatory research design

Six plainly described injected regressions create an easy-task ceiling. A valid effectiveness claim needs **independent historical GitHub issue repairs** with locked, unexposed verifiers, a sufficiently large task sample, isolated VMs/containers, equal model/tool/token and attempt budgets, predeclared task-order randomization, and all failures preserved. Official [SWE-bench Pro V2](https://github.com/scaleapi/SWE-bench_Pro-os/blob/main/v2/README.md) describes a much stronger clean-patch replay design; **this study did not run that benchmark**. <https://mini-swe-agent.com/latest/usage/swebench/> documents a separate runner and evaluation approach.

No recursive model self-improvement, general coding-agent gains, permanent model learning or autonomous system modification has been demonstrated by this six-task result.
