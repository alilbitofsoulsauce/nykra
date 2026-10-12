# Nykra v0.26.0 — PR #1 pre-merge review

**Review type:** focused maintainer-side security, reproducibility, packaging and claim audit; **not** an independent security penetration test or a line-by-line audit of all 189 changed files. PR: https://github.com/alilbitofsoulsauce/nykra/pull/1. Reviewed original head: `4e23b196cfcf963049e7b6a18344115ff432473e` (all seven GitHub Actions jobs green: https://github.com/alilbitofsoulsauce/nykra/actions/runs/38230854126).

## Release gate and changes

The review identified a CI supply-chain and credential-scope improvement. This PR adds:

- An explicit workflow-wide `permissions: contents: read` token policy, with no write or OIDC privileges required.
- `persist-credentials: false` for both source checkouts, so test processes do not need GitHub repository credentials in their Git configuration.
- SHA-pinned **actions/checkout v7** (`3d3c42e5aac5ba805825da76410c181273ba90b1`) and **actions/setup-python v7** (`5fda3b95a4ea91299a34e894583c3862153e4b97`) rather than deprecated Node 20-based majors. Tags were verified against the upstream GitHub Git references during the review; verify again when upgrading.
- An explicit `ubuntu-24.04` hosted runner instead of a migrating `ubuntu-latest` label; Windows/macOS remain on their latest labels and are therefore not fixed-image reproducible.
- `tests/test_ci_security.py` to guard these controls against accidental weakening.

These controls reduce workflow privilege; they do not make execution of an untrusted fork's tests intrinsically safe. Hosted CI is disposable runner infrastructure, but third-party actions, the operating system, dependencies, and GitHub itself remain trust dependencies.

## Boundaries inspected

- **Approval:** `run_transaction`, `multifile_workflow`, and free-provider requests require an explicit approval flag. The supervised multi-file workflow does not invoke a paid model or write to the original repository automatically.
- **Patches:** exact path allowlists, limits on patch size/count, rejection of symlinks and path traversal, disposable pinned-HEAD Git clones, tested-byte verification, lock/revalidation before optional promotion and rollback of affected files are implemented. These are not a certified defense against a hostile local process, race conditions external to the process or the user's own Git configuration.
- **Test execution:** the Docker path requires an immutable image ID, a networkless, read-only, nonroot process and resource limits. Opting into **trusted local tests** executes candidate repository code with the workstation user's privileges; that feature must remain opt-in and unsuitable for hostile patches. Docker restrictions are not a proven sandbox.
- **Cache:** model and public-evaluation caches require exact identities and validate stored checksums (free-model cache uses account-keyed HMAC). Same-account local processes with write access can still alter cache state; generated model text is stored and may be sensitive.
- **Packaging:** runtime dependencies are empty; Python and the VS Code extension identify as v0.26.0. The CI wheel build and isolated-install checks are package smoke tests, not a software bill of materials or dependency-vulnerability assessment.
- **Release files:** `scripts/check_release_inputs.py` screens known token signatures, private-file extensions and excluded paths; it is heuristic and cannot rule out every personal identifier, signed URL, novel token, or proprietary material. `experiments/` is excluded from version control and the public release input set.

## Evidence and performance claims

- The v0.38 recorded subset was **2/2 hidden-verified structured-edit completions versus 0/2 raw-diff completions** under specified budgets, not an independent estimate of general model coding ability.
- The adaptive strategy has **no proven net coding advantage** in the recorded comparisons: the successful v0.36 baseline used 4 calls versus adaptive 7; the v0.40 baseline/adaptive policies both succeeded at the first completion. The v0.39 structured patches passed public tests but failed hidden semantic tests.
- Previously recorded negative outcomes, source/test hashes and frozen protocol receipts must not be rewritten to improve the story. Historical source snapshots preserve bytes when active test code changes.
- **Historical hidden suites exist in the public evidence archive.** They are historical, not secret future holdouts; using those same tasks for a new purported *blind* success claim would contaminate evaluation. Future v0.41 experiments need independently chosen tasks with withheld grading restricted until the terminal arm verdict.

## Outstanding before release

1. Require a green push **and** pull-request GitHub Actions matrix for the exact final review commit after the CI hardening change.
2. Review the broad PR diff for security and licensing concerns, especially historical source excerpts and public model-output receipts. This focused review does not certify third-party copyright or personal-data clearance.
3. Do not auto-merge PR #1, tag v0.26.0, publish a GitHub release, or infer general-purpose agent improvement. These are separate maintainer decisions.

**Focused review verdict:** proceed to hosted verification, then independent maintainer review; no identified release-blocking code-execution bypass was demonstrated in the reviewed paths. Absence of a demonstrated bypass is not proof that one does not exist.
