# Nykra 0.26.0 — local release-candidate checklist

**Status: release-candidate branch pushed to GitHub for CI review; NOT merged into `main`, tagged, or published as a release.** The latest published tag remains `v0.25.0`.

## Release scope

- Core: approval-gated multi-file transactions, supervised Git/Docker public-evaluation workflow, exact-request/public-result reuse, and strict JSON source-edit to diff conversion.
- Agent independence: model proposals are user-supplied or explicitly delegated; no required paid model, automatic provider installation or unrestricted unattended execution.
- Evidence: historical benchmark and raw receipts through v0.40, including unfavorable or inconclusive adaptive-policy results. Original v0.37 adapter/test files and the pre-portability-fix v0.30/v0.32/v0.37/v0.40 CI tests are archived byte-for-byte with verified SHA-256 digests; active source is separately hardened against malformed Unicode.
- Product metadata: Python distribution, `nykra.__version__`, and VS Code observer extension all identify as `0.26.0`.

## Verify on a clean release candidate

```sh
python -m pip install -e .
python -m unittest discover -s tests -p test_transactional_patch.py -v
python -m unittest discover -s tests -p test_multifile_workflow.py -v
python -m unittest discover -s tests -p test_structured_edit_adapter.py -v
python -m unittest discover -s tests -p test_evidence_registry.py -v
python -m unittest discover -s tests -p test_release_candidate.py -v
python -m unittest discover -s tests -p test_release_inputs.py -v
python scripts/check_release_inputs.py --include-untracked
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python -m nykra demo
python -m nykra --version
```

The GitHub Actions matrix defined in `.github/workflows/ci.yml` is **the actual cross-platform release gate**: Python 3.10 and 3.13 on Ubuntu, Windows and macOS. Locally passing Windows/Docker smoke tests do not imply all six hosted matrix jobs have passed. The ordinary unrestricted historical-test discovery can require unavailable ignored upstream sources and can exceed a short timeout; do not mislabel that as a clean-clone CI success.

## Locally observed candidate results (October 12, 2026)

- **Windows, Python 3.13:** all 24 configured CI test modules passed, **162 individual tests**. The supervised multi-file workflow module took approximately 49 seconds; it must not be given an artificial 45-second timeout.
- **Linux, Python 3.13:** five offline commands passed inside a networkless, read-only, nonroot Docker container against an isolated candidate copy: version, synthetic demo, release-candidate test module, source-normalizer tests, and free-model-client tests. The local Python slim image lacks Git, so this was **not** the complete Linux CI job.
- **Release package:** the `nykra-0.26.0-py3-none-any.whl` wheel built offline without dependencies, contained 84 entries, and independently installed and executed the CLI version and demo; embedded VS Code extension version was checked.
- **Git candidate:** 509 eligible files scanned for known credential signatures, no matches; `git add --dry-run -A` identified 182 pending staging actions without staging or committing anything. Both counts were observed before final documentation edits and are not immutable release identifiers.
- **First hosted matrix run:** [GitHub Actions run 38225963342](https://github.com/alilbitofsoulsauce/nykra/actions/runs/38225963342) against commit `755c305` confirmed the release-hygiene job passed but the six OS/Python matrix jobs failed because two historical test assertions assumed more than a clean clone guarantees. On Python 3.10, an empty `unittest` discovery can exit 0; Nykra correctly marks `tests_run == 0` as failure, so the test no longer assumes an exit code. Other jobs lacked ignored upstream Git checkouts; the optional external source replay test now explicitly skips without its prerequisites while other frozen evidence tests still run. This is an honest record of the unsuccessful first CI run, not a successful release gate.
- **Second hosted matrix run:** [GitHub Actions run 38227092657](https://github.com/alilbitofsoulsauce/nykra/actions/runs/38227092657) passed its release-hygiene job and the previously failing v0.30/v0.32 tests, then exposed two further tests depending on ignored upstream Git repositories (v0.37 patch replay and v0.40 PySnooper reconstruction). These were split into unconditional raw-evidence integrity checks and separately optional pinned-source reconstruction checks. The original tests were archived with unchanged SHA-256 hashes.
- **Full clean-clone audit:** A separate throwaway local Git clone (without any ignored `experiments/` sources) exercised all 24 configured CI modules, revealing that Git's LF checkout normalization changed the byte-level checksum of `tests/test_zero_count_public.py` (without changing its source lines). The original CRLF bytes are now preserved in `docs/evidence/v26_original_zero_count_public_tests.py.txt`; the active manifest records the committed LF blob SHA. No historical outcome receipt was modified.
- **Retest status:** Follow-up corrections passed 24 supervised workflow tests on Windows and the v0.32 recovery module on Linux Python 3.13 (one explicit optional-checkout skip). The v0.37/v0.40 evidence modules also pass in a true clean clone with one transparent optional reconstruction skip each. The next exact GitHub CI must still pass before release. The unrestricted historical test discovery exceeded 180 seconds in a prior run and does not replace the explicit clean-clone test list.

## Release publication gate

1. Confirm every intended development file is accounted for (including ignored paths staying excluded); run `git diff --check` and the pending-file secret-pattern scanner. Scanner coverage is heuristic, not a professional secret audit.
2. Verify all manifest hashes and archived original-source bytes; historical negative outcomes must remain unchanged. Review any new source edits and all test commands.
3. Review an explicit Git staging manifest and perform a scoped maintainer-approved commit; do not stage `.env`, `experiments`, machine-specific state or credentials.
4. Open a PR and observe the actual hosted GitHub Actions matrix and release hygiene job passing on the exact commit.
5. Only after approval and CI success, merge/tag `v0.26.0` and publish release notes. No steps above are permission to push, tag or publish automatically.

## Honest claims

A bounded structured-edit adapter solved 2 of 2 newly selected historical two-file issues in v0.38, while the raw Git-diff arm solved 0 of 2 within its recorded call budgets. A v0.39 structured run produced valid public-passing patches but failed hidden semantic checks. In v0.36, adaptive rerooting used **seven calls versus four for the baseline**, both ultimately solved; v0.40 both policies solved in one call with no fork. Nykra therefore has concrete workflow and format-reliability evidence, **not a demonstrated general adaptive-agent improvement**. See `docs/EVIDENCE.md` and `docs/CROSS_REPO_MODEL_POLICY_V40.md` for raw methods and limits.
