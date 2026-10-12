# Supervised multi-file agent workflow (v0.26 development)

Nykra now has a **separate, portable multi-file proposal lifecycle** that uses the
existing v0.25 safe Git patch evaluator. This is a **development feature**, not
a v0.26 tagged release or a proof that any coding model solves more tasks.

## What it does

An external agent (ChatGPT + Rel.AI, Codex, OpenCode, a human, etc.) authors a
UTF-8 Git diff. Nykra selects whether to request an independent attempt or
a revision using the provider-neutral depth/breadth/adaptive policy. It tests
the diff in a disposable Git checkout, captures bounded public-test feedback,
persists attempted diffs and SHA-256 fingerprints in per-user Nykra history,
and selects a passing public-test patch at finalization.

**No model call is made by Nykra.** **No hidden evaluator exists in this
workflow.** It never promotes, commits, pushes or writes to the original
repository. A passing public test does *not* establish correctness against
independent hidden checks or security against hostile tests.

Requirements: Python 3.10+, Git, a clean committed repository with tests
available via Python unittest. A locally installed pinned Python Docker image
is required by default; a trusted local-only test mode is permitted only by
an explicit separate flag for repositories whose tests you personally trust.

## Supervised CLI lifecycle

Use a clean checkout and explicitly name every file that the agent may alter.

```sh
python -m nykra multi-workflow start --repository /path/to/repo \
  --task "Fix the invoice calculation and route together" \
  --allow engine/calc.py --allow engine/routes.py \
  --policy adaptive --budget 4 \
  --docker-image-id sha256:YOUR_64_HEX_IMAGE_ID --approve
```

The JSON result includes a generated `session_id` and a request to the agent.
Read subsequent requests with:

```sh
python -m nykra multi-workflow next --session SESSION_ID
```

The supervising agent writes its proposed full Git diff to `proposal.diff`.
Pass it back to the sandbox evaluator:

```sh
python -m nykra multi-workflow submit --session SESSION_ID \
  --candidate-file proposal.diff --approve
```

Use the next request if public tests fail; the response includes the public
test status, bounded (untrusted) diagnostic and the previous patch file path
when a revision is requested. Each proposal counts toward the declared attempt
budget; Docker infrastructure errors fail closed without consuming one.

For deterministic public tests, add `--dedupe-public` **at session start** to
reuse an already evaluated, byte-identical failed patch **within that session**.
This opt-in does not make or save model calls, and a repeated proposal still
consumes one model attempt; only redundant Git/Docker public grading is skipped.
The response marks `public_test_reused`, `reused_from_attempt_id`, and
`public_tests_executed_now`, while `summary` and `finalize` expose
`public_work.public_evaluator_calls` versus `public_evaluator_reuses`.
A repeated receipt is only eligible after the original repository has again
passed clean-HEAD checks and the submitted patch passes the strict allowlist
parser. The original saved patch file is re-read and byte-compared; an
invalid/infrastructure-failed patch cannot be reused. This assumes stable,
deterministic public tests; do not enable it for flaky or environment-sensitive
tests. The default is **off**, and no reuse crosses a session boundary.

```sh
python -m nykra multi-workflow summary --session SESSION_ID
python -m nykra multi-workflow finalize --session SESSION_ID --approve
```

Finalization reports a selected patch file and SHA-256 digest only if a
submitted candidate passed public tests. Nothing is applied to the real repo.
To apply the verified candidate after separately reviewing it, repeat the
actual `patch-transaction` with explicit `--promote --approve`, allowing
exactly the chosen paths. That action retests the patch before promotion.

For **trusted synthetic/local fixtures only**, replace `--docker-image-id`
with `--trusted-local-tests`. Never run this mode on untrusted generated or
third-party code: tests run with your workstation user privileges.

## Security and experimental boundaries

- Explicit approved session, bounded 1–6 attempts, 1–16 exact allowlisted
  paths, max 128 KiB diff and max 2 MiB file outputs (transaction engine).
- Pinned Docker image, read-only repo mount, disabled networking, restricted
  privileges and resource caps by default; Docker is *not* a certified sandbox.
- Clean Git state and original HEAD pinned at session start; stale/dirty
  revisions are refused. A zero-test unittest run is never credited as success;
  the transaction receipt records `tests_run`. This count is parsed from
  unittest stderr and is not tamper-proof against deliberately hostile code.
  Parent choices use only observed public outcomes.
- Per-user local state is not proof against a malicious local account owner;
  do not import arbitrary session directories from strangers.
- Public-test feedback is untrusted. The workflow exposes no hidden test bodies.
- Unsupported today: autonomous model generation, independent hidden grading,
  **cross-session** public-cache reuse for arbitrary multi-file diffs, non-Python tests, crash
  recovery of interrupted submissions, verified native second-agent adapters,
  and unbiased proof of general coding uplift.

## Reproduce without external historical repositories

```sh
python -m unittest discover -s tests -p test_multifile_workflow.py -v
python -m unittest discover -s tests -p test_transactional_patch.py -v
python -m nykra demo
```

The tests use a fresh synthetic two-module Git fixture, real Git diffs and
Python unittest checks; they do not benchmark authenticated model inference.

A separate, genuine evaluator defect was reproduced and repaired with an
agent-authored two-module patch: see [v0.26 zero-test issue report](REAL_ISSUE_V26.md)
for exact reproducible evidence and limitations.
