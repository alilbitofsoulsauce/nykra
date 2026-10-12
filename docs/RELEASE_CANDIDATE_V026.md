# Nykra 0.26.0 — local release-candidate checklist

**Status: local working-tree candidate; NOT committed, pushed, tagged, or published.** The only published repository tag at preparation time was `v0.25.0`.

## Release scope

- Core: approval-gated multi-file transactions, supervised Git/Docker public-evaluation workflow, exact-request/public-result reuse, and strict JSON source-edit to diff conversion.
- Agent independence: model proposals are user-supplied or explicitly delegated; no required paid model, automatic provider installation or unrestricted unattended execution.
- Evidence: historical benchmark and raw receipts through v0.40, including unfavorable or inconclusive adaptive-policy results. Original v0.37 adapter/test files are archived byte-for-byte; active source is separately hardened against malformed Unicode.
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
- **Outstanding:** Python 3.10, macOS and the actual hosted GitHub Actions matrix remain unverified. The unrestricted historical test discovery exceeded 180 seconds in a prior run, and does not replace the explicit clean-clone test list.

## Release publication gate

1. Confirm every intended development file is accounted for (including ignored paths staying excluded); run `git diff --check` and the pending-file secret-pattern scanner. Scanner coverage is heuristic, not a professional secret audit.
2. Verify all manifest hashes and archived original-source bytes; historical negative outcomes must remain unchanged. Review any new source edits and all test commands.
3. Review an explicit Git staging manifest and perform a scoped maintainer-approved commit; do not stage `.env`, `experiments`, machine-specific state or credentials.
4. Open a PR and observe the actual hosted GitHub Actions matrix and release hygiene job passing on the exact commit.
5. Only after approval and CI success, merge/tag `v0.26.0` and publish release notes. No steps above are permission to push, tag or publish automatically.

## Honest claims

A bounded structured-edit adapter solved 2 of 2 newly selected historical two-file issues in v0.38, while the raw Git-diff arm solved 0 of 2 within its recorded call budgets. A v0.39 structured run produced valid public-passing patches but failed hidden semantic checks. In v0.36, adaptive rerooting used **seven calls versus four for the baseline**, both ultimately solved; v0.40 both policies solved in one call with no fork. Nykra therefore has concrete workflow and format-reliability evidence, **not a demonstrated general adaptive-agent improvement**. See `docs/EVIDENCE.md` and `docs/CROSS_REPO_MODEL_POLICY_V40.md` for raw methods and limits.
