# Nykra v0.18 — Cross-repository repair with withheld final tests

## Question and implementation

Does Nykra's shared adaptive exploration policy increase **full-task repair success** versus the same Codex model operating under the baseline depth/revision policy?

The frozen study ran four real historical issues from the published [BugsInPy benchmark](https://github.com/soarsmu/BugsInPy): three issues in [youtube-dl](https://github.com/ytdl-org/youtube-dl) and one in [PySnooper](https://github.com/cool-RR/PySnooper). They were not synthetic Nykra mutations. The unit of analysis is **one issue**, not an individual assertion.

- Frozen final protocol: [v18_protocol.json](evidence/v18_protocol.json), SHA-256 `8d52ce33e9906211e3e2a39ab16b65eeb4bd0f3d92b2f0bf6604898f12d954b6`.
- Before model calls, the Python 3.8 + pytest image was amended to include PySnooper's 2019 test dependencies. The [original preflight protocol](evidence/v18_protocol_preflight_original.json) and its hash are preserved. This was an environment amendment **before any model proposals**, not a post-result task-selection change.
- Frozen hidden behavioral checks: `nykra/v18_hidden_spec.py`, source hash recorded in the protocol.
- Both arms used the same authenticated `gpt-6-luna` low-effort Codex executor, the same first prompt format, the same public pass/fail feedback, a maximum of three model calls per issue, 70 seconds per call, 200 total model seconds per arm, and a soft 42,000 reported-token ceiling per arm. Actual token usage and overshoots are retained.
- Baseline controller: Nykra's shared `depth` parent/revision policy. Nykra controller: its actual shared `adaptive` ancestor/branch policy.
- Codex generated a single complete replacement for one upstream top-level Python function. It did not receive the reference fix, hidden source or hidden test outcomes. This is narrower than unrestricted multi-file coding-agent repair.

## Actual results

| Real issue | Baseline full public + hidden success | Nykra full public + hidden success | Notes |
| --- | --- | --- | --- |
| youtube-dl bug 17 — `cli_bool_option` | **Pass**, 1 attempt | **Pass**, 1 attempt | Both correct immediately |
| youtube-dl bug 20 — `get_elements_by_attribute` | Fail, 3 attempts | Fail, 3 attempts | No candidate reached hidden grading |
| youtube-dl bug 21 — `urljoin` bytes handling | Fail, 3 attempts | **Pass**, 2 attempts | Nykra-only successful held-out repair |
| PySnooper bug 3 — `get_write_function` | **Pass**, 1 attempt | Fail, 3 attempts | Baseline-only successful held-out repair |
| **Total (4 issues)** | **2/4 (50%)** | **2/4 (50%)** | **Net difference: 0 percentage points** |

There was one success unique to each arm, one joint success, and one joint failure. The two-sided exact paired sign p-value is **1.0** (n=2 discordant pairs). Given only four issues, this is not a precise estimate of general effect.

- Sum of *model-reported* tokens: **47,242** baseline; **54,427** Nykra. No efficiency conclusion; model token counters may reflect internal accounting rather than costs, and caps are not hard within a call.
- **Critically, zero tasks showed a differing exploration-policy decision along comparable attempts.** At a three-attempt cap the adaptive reset on stagnation was not exercised. The differing model answers may be explained by stochastic inference alone. The isolated Nykra-only win is **not attributable to branching**.
- All four defects passed the pre-inference eligibility gate: buggy source failed both the upstream public reproducer and withheld behavioral check; official reference fix passed public and hidden checks in the same evaluator environment. No infrastructure exclusions occurred.

[Machine-readable summary](evidence/v18_summary.json). Raw model attempts and evaluator results: [youtube-dl 17](evidence/v18_youtube_dl_17.json), [youtube-dl 20](evidence/v18_youtube_dl_20.json), [youtube-dl 21](evidence/v18_youtube_dl_21.json), [PySnooper 3](evidence/v18_pysnooper_3.json). Each includes its frozen-protocol SHA-256, source text and candidate hashes, public grader results, terminal hidden grader outcome, attempts, parent ancestry and usage.

## Independent verification and security boundary

For each public or hidden grade, Nykra exported the recorded upstream buggy Git commit, injected the upstream regression test file from the fixed commit, and generated a trusted Dockerfile containing `FROM`, `COPY`, and nonroot configuration. No untrusted repository setup commands were run during the image build. Reference and generated repairs were applied only to temporary copies. An immutable locally verified Python 3.8 image ID was pinned in the protocol.

The separate hidden suite combines evaluator-owned, preregistered behavioral inputs with upstream tests not used for public feedback. **Only the selected public-passing candidate** received one final hidden evaluation, without leaking hidden feedback to the model.

Container execution used no network, a read-only root, UID 65534, dropped capabilities, no-new-privileges, no host directory mounts, memory/CPU/process limits and timeouts. This reduces exposure, but neither Docker Desktop on Windows nor these flags certify isolation against adversarial code. The benchmark is **not an official BugsInPy harness score or an official SWE-bench result**.

## Interpretation and next protocol

This pilot achieved reproducible **cross-repository testing with genuinely withheld final cases**, and recorded both favorable and unfavorable model results. **It did not show a task-success uplift for Nykra or a causal adaptive-policy benefit**.

A useful next controlled experiment must explicitly force or preregister an actual policy fork: run at least four attempts per arm, use a **common frozen first candidate** in both arms to reduce first-sample randomness, provide richer identical public failure feedback, and independently grade the selected final candidate using held-out tests. Include substantially more diverse real issues, fully count exclusions, and separate demonstrated policy differences from random variation. Pairing two identical decision sequences under different policy labels is not evidence of policy effectiveness.

Re-run local checks using `python -m unittest discover -s tests -p test_real_issue_v18.py -v`. The complete earlier results remain immutable. No commit, release or push was made by this study.
