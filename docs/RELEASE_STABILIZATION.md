# Nykra development-branch stabilization

This report covers the unreleased development branch after the v0.40 historical experiments. It does not announce a published release or establish generalized coding-agent superiority.

## Verified release gates

- All 21 existing clean-clone CI unittest modules passed when the multi-file workflow module was allowed to finish. The latter ran 24 tests in 49.467 seconds; the earlier 45-second investigation limit was insufficient.
- The new release-scanner regression passed, and the structured-edit adapter passed seven tests including malformed Unicode rejection.
- The evidence registry passed all six tests after current-source SHA-256 values were updated.
- The opt-in tracked-plus-untracked release scan checked 507 Git-eligible paths, finding no matches for its known credential signatures. This scanner is not a comprehensive secret-detection service.
- A disposable copy of 507 eligible files compiled successfully and produced a wheel using offline packaging. The wheel installed into a separate target directory and its CLI version and synthetic demo succeeded.
- Git whitespace verification passed after normalizing the evidence manifest line endings to LF; the JSON evidence values were not changed except the two current-source hashes described below.
- Docker 29.8.2 completed the fixed-command restricted smoke using locally cached `busybox@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e`. This does not certify hostile-code isolation.

## Adapter hardening and historical provenance

Malformed surrogate Unicode supplied by a model now produces `PatchRejected` rather than an uncaught `UnicodeEncodeError`. That failure path was added to the unit tests. Normal well-formed patch construction and the historical trial outcomes were not reclassified.

The *exact pre-hardening source bytes* were preserved separately, and their SHA-256 digests match the earlier evidence manifest:

| Historical file snapshot | Original SHA-256 |
| --- | --- |
| `docs/evidence/v37_original_structured_edit_adapter.py` | `adac639e6aa7f473c33718651bf81d56c82d5393b18f812082ac7caf9fea9f87` |
| `docs/evidence/v37_original_structured_edit_tests.py` | `99bb2d05dd15de8e840c3039b0792233cbb72fedb1fe577a50be921c8f0d1c53` |

The manifest entries for the active `nykra/structured_edit_adapter.py` and `tests/test_structured_edit_adapter.py` now point to the post-hardening current files, **not** to the frozen versions exercised in the earlier studies. The historical trial artifacts and negative outcomes were left unchanged.

## Limitations and publication gates

- The unrestricted legacy test discovery did not complete within 180 seconds, primarily while processing historical fixtures and warning-heavy source evaluations; it must not be reported as a full-suite pass.
- The package remains version 0.25.0, and published `main` remains at the v0.25.0 baseline. Development results through v0.40 are not yet a tagged release.
- Local Windows tests and a disposable packaging trial do not substitute for the configured GitHub Actions Linux/macOS/Windows and Python 3.10/3.13 matrix.
- Historical tasks and locally authored frozen hidden fixtures do not establish a statistically general advantage or independent benchmark performance.
- Neither benchmark patch promotion nor Git commit, push, or publication was performed in this stabilization task.

The next release action is an explicit maintainer review of this development branch and its evidence archive, followed by a deliberate release version/CI/publish workflow. The next research milestone is a pre-registered, independent v0.41 evaluation on new upstream issues.
