# v0.39–v0.40: Cross-repository structured edits and model-availability limits

## What this actually establishes

Nykra was tested on historical **PySnooper Bug #1** (a Python tracing library),
a new repository relative to the earlier youtube-dl-only v37–v38 study.
The real upstream bug touches two production files:
`pysnooper/pycompat.py` and `pysnooper/tracer.py`, covering Unicode
source decoding, UTF-8 trace output, and compatibility flags.

The original buggy Git revision and official upstream fixed revision were
used for independent Docker prevalidation. For the first study (v39),
buggy public **FAIL**, buggy hidden **FAIL**, official fixed public **PASS**
and fixed hidden **PASS**. An initial source-grader mapping error was
retained in `v39_pysnooper_preflight.json`; the corrected, eligible
pre-model evidence is `v39_pysnooper_preflight_validated.json`.
Both test suites were authored and SHA-256-frozen before the first v39
coding-model call.

### v39 — Original cross-repository study, GPT-5.6 Luna

| Observed outcome | Raw Git-diff baseline | Nykra structured adapter |
|---|---:| ---:|
| New authenticated Codex model completions | 5 | 5 |
| Invalid/non-applicable Git proposals | 5 | 0 |
| Real public Docker evaluations | 0 | 5 |
| Public-passing proposals | 0 | 5 |
| Original hidden Docker evaluations | 0 | 5 |
| **Hidden-verified solution within five calls** | **No** | **No** |
| Reported input tokens, including cached | 192,223 | 126,494 |
| Reported output tokens | 3,884 | 3,692 |

**Negative result for semantic correctness:** all five structured
proposals passed the public regression but failed the frozen hidden
suite. Most adjusted the tracer's Unicode decoding but did not make
the necessary compatible changes to both modules. Although the adapter
eliminated the patch-serialization blocker, a testable patch was not
necessarily a complete repair.

**Protocol flaw identified retrospectively:** the v39 runner re-ran
hidden checks after successive public-passing proposals. It did not
show hidden assertion text to Codex, but repeatedly using hidden
pass/fail to continue exploration is still inappropriate for a
strictly held-out benchmark. The receipts are preserved as a development
study and should **not** be called an independently blind accuracy
comparison after repeated hidden probes.

### Provider independence probe

No `OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `COHERE_API_KEY` was available in the
local execution process (values were never read or printed).
`opencode run --pure --model opencode/mimo-v2.6-flash-free`
did not return an auditable model response before the authorized
execution deadline; `docs/evidence/v39_opencode_provider_probe.json`
records this blocker. The second independent provider remains
**unverified/unavailable**, not secretly replaced by a model simulator.

Native Codex `gpt-5.6-terra`, in contrast, produced an authenticated
real response. It is a different model from `gpt-5.6-luna` but is
**the same provider and the same ChatGPT Codex account**.
The readiness receipt is `v39_second_codex_model_probe.json`.

### v40 — Follow-on posthoc study, GPT-5.6 Terra (same provider)

Having observed the v39 failure, the public PySnooper regression was
**explicitly strengthened**, covering the relevant second production
file and UTF-8 output behavior. A *new* frozen public suite and *new*
evaluator-only hidden suite were authored and hashed before any Terra
coding-model proposals. Actual Docker prevalidation again confirmed
buggy **FAIL/FAIL** and official fixed **PASS/PASS**.

This is a **posthoc follow-on on an already investigated upstream bug**,
not a new unseen blind model-family comparison. The two Terra arms used
the **same model, identical first prompt, exactly the same bounded
structured-edit adapter, the same public-only feedback, and the
same five-call ceiling**. Only controller policy differed:

| Actual outcome | Depth policy | Adaptive policy |
|---|---:|---:|
| Distinct authenticated Terra completions | 1 | 1 |
| Changes made to both registered production files | Yes | Yes |
| Real Docker public suite | PASS | PASS |
| Real Docker hidden suite | PASS | PASS |
| Independent later real Docker public + hidden regrade | PASS / PASS | PASS / PASS |
| Reported input tokens | 17,177 | 17,173 |
| Reported output tokens | 568 | 564 |
| Controller fork observed | **No** | **No** |

Both model-generated patches were independently regenerated and
verified in restricted, pinned, networkless Docker. Neither arm
required revision or rerooting: both solved on their first new model
completion. Accordingly **this provides no evidence of adaptive-policy
superiority**, nor an unbiased head-to-head model comparison with Luna.

**New holdout safety rule:** the v40 runner grades hidden checks
**once**, only after the *first public-passing proposal*, then
terminates that arm whether hidden passes or fails. A hidden failure
must never become feedback for another proposal. This is a more
conservative benchmark protocol and prevents repeated hidden probing.

## Security, scope, and reproducibility

All model proposals remain outside the Nykra Git repository. Models
return bounded exact-source-edit JSON, Nykra builds applicable Git
patches without executing target source, and separate Docker graders
verify behavior in an offline, capability-restricted container.
Candidate source is **not** executed on Windows.

Frozen protocols and private validators:

- `docs/evidence/v39_pysnooper_protocol.json`
- `docs/evidence/v39_public_pysnooper1.py`
- `docs/evidence/v39_hidden_pysnooper1.py`
- `docs/evidence/v39_pysnooper_preflight.json` (failed-infrastructure
  first preflight; retained)
- `docs/evidence/v39_pysnooper_preflight_validated.json` (eligible)
- `docs/evidence/v39_pysnooper_live/` (both complete real Luna arms)
- `docs/evidence/v39_opencode_provider_probe.json`
- `docs/evidence/v39_second_codex_model_protocol.json` and
  `docs/evidence/v39_second_codex_model_probe.json`
- `docs/evidence/v40_terra_policy_protocol.json`
- `docs/evidence/v40_public_pysnooper_terra.py`
- `docs/evidence/v40_hidden_pysnooper_terra.py`
- `docs/evidence/v40_terra_preflight.json`
- `docs/evidence/v40_terra_policy_live/` (two distinct Terra calls)
- `docs/evidence/v40_independent_regrade.json`

Development code:

- `nykra/v39_pysnooper_grader.py` and `nykra/v40_terra_grader.py`
- `scripts/run_crossrepo_pysnooper_v39.py` and
  `scripts/run_terra_policy_v40.py`
- `tests/test_v39_v40_crossrepo_evidence.py`

## Subsequent research priorities

1. **Provider diversity:** independently authenticate a usable
   non-Codex coding provider, and score new coding proposals rather
   than claiming free provider availability from catalog listings.
2. **Adaptive exploration:** pre-register a *new unseen* case with
   identical structured outputs for both arms, meaningful public
   failures and a potential actual reroot, withholding hidden checks
   until one final candidate per arm.
3. **Semantic coverage:** add requirements-tracing across multiple
   modules and distinct behavior classes; passing one narrow public
   fixture must not be mistaken for satisfying the whole task.
4. **External benchmark credibility:** use established multi-project
   code-repair suites and official hidden assessment when permissible.

Both v39 and v40 are development experiments, not product release
claims. No changes were committed, pushed, published, or promoted.
