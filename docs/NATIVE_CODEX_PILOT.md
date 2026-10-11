# Native Codex v0.14: Real Model Comparison

**Executed October 11, 2026 using Rel.AI as the primary workstation driver.**
**Agent:** official OpenAI Codex CLI v0.160.0, running the ChatGPT-authenticated **gpt-6-luna** model, reasoning effort **low**. Codex was installed *alongside*, not *instead of*, Rel.AI.

## Provenance and runtime

Nykra downloaded the official Windows release from the GitHub tag `rust-v0.160.0` into a dedicated per-user Nykra runner directory, resumed a slow HTTP download, and verified the ZIP **SHA-256 `aad5cf364c873b148e462b58fd06ad7b37fcab9b996be67133386b9322df26bb`** against the published release asset digest before extracting it. The native CLI responded to `--version` with `codex-cli 0.160.0`, reported **Logged in using ChatGPT**, and subsequently completed a real read-only, noninteractive inference prompt with exactly `NYKRA_NATIVE_INFERENCE_OK` in 9.4 seconds. No new API key was installed, and Nykra did not directly charge an API key. ChatGPT plan usage and token/resource consumption can still apply.

A first probe erroneously used the user's unsupported `gpt-5.6-sol` configuration; the server refused that model on ChatGPT authentication. The verified invocation instead used a supported model through Codex with `--ignore-user-config`. A model prompt was provided with `stdin=DEVNULL` to avoid the interactive-input hang observed during initial smoke testing. The agent ran with read-only filesystem sandbox, no tool invocation requested, and independent fresh temporary directories. A read-only CLI sandbox is not an independent secure environment for untrusted third-party code; candidate execution also uses Nykra's AST-restricted worker, **not a hardened OS security boundary**.

## Task set and scoring

Exactly four fixed, synthetic Python *function-level bug repair* challenges: `reservation-gaps`, `ledger-undo`, `csv-records`, and `normalized-path`. Each has a published defective implementation, a specification, 14 public training examples and 32 different held-out examples with **zero duplicate input overlap**. Code is executed in a restricted child Python process. Held-out results are computed only after the highest-training-scored candidate is selected; held-out expected outputs are not placed in the model prompt.

Both arms use the **same actual Codex model, reasoning effort, initial prompt, training feedback, two-attempt maximum, 75-second per-turn timeout, and scorer**. Orders were counterbalanced by task (two baseline-first, two Nykra-first).

**Baseline policy:** a fresh independent implementation on a second attempt, provided the same previous code and feedback.

**Nykra-labelled policy:** revise the previous implementation on the second attempt, guided by validator/test failures.

This tests a **specific Nykra-style revision prompt**, **not** Nykra's full learned search policies, persistent history transfer, arbitrary agent autonomy or recursive self-improvement. The "Nykra-guided" label refers solely to that fixed policy instruction; all other relevant evaluation controls were kept the same. The benchmark is not SWE-bench, was not externally blinded, and contains only four challenge families.

## Original registered pilot — v1

- Frozen protocol: [v1 protocol](evidence/v14_codex_pilot_protocol.json)
- Raw completed runs: [reservation-gaps](evidence/v14_codex_reservation-gaps.json), [ledger-undo](evidence/v14_codex_ledger-undo.json), [csv-records](evidence/v14_codex_csv-records.json), [normalized-path](evidence/v14_codex_normalized-path.json)
- [Machine-readable summary](evidence/v14_native_codex_v1_summary.json)

| Metric | Baseline | Nykra-guided |
| --- | ---: | ---: |
| Fully solved tasks | **1/4** | **1/4** |
| Hidden test cases passed | **32/128** | **32/128** |
| Model attempts executed | 4 | 4 |

**Interpretation:** No observed advantage. Both passed only the reservation-gap task. The three other tasks produced invalid source under Nykra's unusually restrictive AST code interface. Importantly, v1 incorrectly stopped the arm on invalid source rather than invoking the second allowed attempt. These are real end-to-end runner observations, but they measure the interface as much as coding behavior.

## Post-hoc validation-feedback repair follow-up — v2

- Independently frozen [amendment protocol](evidence/v14_codex_pilot_protocol_v2.json), written **after** inspecting v1 failures; not a replacement for v1.
- Raw runs: [reservation-gaps](evidence/v14_codex_v2_reservation-gaps.json), [ledger-undo](evidence/v14_codex_v2_ledger-undo.json), [csv-records](evidence/v14_codex_v2_csv-records.json), [normalized-path](evidence/v14_codex_v2_normalized-path.json)
- [Machine-readable v2 summary](evidence/v14_native_codex_v2_summary.json)

| Metric | Baseline | Nykra-guided |
| --- | ---: | ---: |
| Fully solved tasks | **1/4** | **1/4** |
| Held-out test cases passed | **32/128** | **37/128** |
| Model attempts executed | **7** | **7** |
| Total model-reported tokens | **56,723** | **56,686** |
| Sum of measured model-call wall time | **90.92 s** | **78.57 s** |

Task outcomes:

| Task | Baseline hidden checks | Nykra hidden checks | Interpretation |
| --- | ---: | ---: | --- |
| Reservation gaps | 32/32 | 32/32 | Both solved immediately |
| Ledger cancellation | 0/32 | 0/32 | Both attempts failed restricted-source checks |
| CSV parsing | 0/32 | **5/32** | Nykra's second attempt became syntactically allowed but remained largely incorrect |
| Normalized path | 0/32 | 0/32 | Both arms failed restricted-source checks |

The **five extra passing CSV cases are not an additional solved task**. V2 showed **no full-task win for either arm**. The wall-time difference is descriptive, highly variable with task/model latency, and is not a demonstrated speed advantage. "Reported tokens" is the Codex CLI's own counter and does not independently establish billing or cost savings. Test cases are correlated within four tasks and **must not be treated as 128 independent model-repair experiments**.

The v2 retry system preserved previous invalid source and deterministic AST error text, gave **the same validation feedback** to both arms, and used the second attempt fairly. The labels describe generation strategies, not statistical evidence for a generally superior Nykra policy. No statistical significance, improvement causality, or transfer across agents can be inferred from n=4.

## Reproduction and integrity

From the repository:

```powershell
python -m unittest discover -s tests -p test_native_codex_pilot.py -v
python -m unittest discover -s tests -p test_native_codex_pilot_v2.py -v
python -m unittest discover -s tests -p test_evidence_registry.py -v
```

The stored evidence is reproducible without rerunning model inference: hashes of protocols and complete arm outputs are checked by the evidence registry and compared with summary totals. To reproduce inference, a user must have a working authenticated Codex CLI at the current experimental runner path and explicitly opt in. **Never rerun with the same output filename**: experiment files refuse overwrites, protecting the original results.

## Conclusions and next research gate

1. **Proven engineering:** authenticated headless native Codex inference actually works under Rel.AI orchestration; code can be generated, validated, scored and logged without manually sending every revision.
2. **Not proven:** Nykra's exploration policies improve full-task success rates over an independent-restart baseline, that learning is persistent, or that cross-agent generalization works.
3. The AST restrictor is significantly narrower than ordinary Python and caused most failures. A future study should test real patches in isolated VMs/containers with normal language features rather than weaken a security-sensitive worker ad hoc.
4. A future **preregistered, independently graded repository issue benchmark** should use enough tasks, the same model, equal tool/token/time/attempt budgets, separate workspaces, preserved failed runs and randomized task/arm order. It must not cherry-pick failures from these four tasks.
