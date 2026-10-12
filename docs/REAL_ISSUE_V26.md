# v0.26 — Real Nykra zero-test verdict repair

The Nykra v0.25 transaction engine incorrectly regarded exit code 0 as
sufficient evidence that a Python unittest suite passed. A live pinned Python
3.8 Docker run discovered **zero tests**, exited with **0**, and Nykra reported
`tests_passed=true`. This is a genuine defect in Nykra's evaluator logic,
not an injected coding benchmark bug.

The developer-facing v0.26 supervisor separately rejected some zero-test
claims, but the transaction engine itself did not count tests and the session
receipt omitted the count. These two modules were the approved patch targets.

## Frozen test and actual repair

Before the model proposal, six public regression cases were frozen in a
disposable Nykra Git snapshot. The buggy implementation produced **five
errors and one failure**. The ChatGPT-authored, two-file Git diff was submitted
as one candidate through Nykra's `multi-workflow` API, with a pinned Python
3.13 Docker evaluator and an adaptive policy budget of six.

**Result: one attempt, six of six public checks passed**; the workflow
selected `attempt-1`. Its exact SHA-256 Git diff is retained at
[agent patch](evidence/v26_zero_unittest_agent_patch.diff).
No reference solution was submitted and no model-generated patch was
automatically applied to the original benchmark source.

After proposal generation, twelve additional regression cases were authored
and run separately in the restricted Docker environment. **Twelve of twelve
passed.** These cases were not agent public feedback, but they were written
by the same assistant after seeing the proposal and are **not independently
blinded**. The source is archived at
[additional checks](evidence/v26_zero_unittest_independent_checks.py).

Most importantly, the exact original failure was repeated against the
proposed code using a real Python 3.8 Docker runner:

| Actual Docker evaluation | Exit | Discovered tests | Fixed verdict |
| --- | ---: | ---: | --- |
| Empty suite | 0 | 0 | Rejected |
| One passing test | 0 | 1 | Accepted |

The original disposable source repository remained unmodified by
`multi-workflow`. After these checks, the selected patch was applied to
the *development feature branch*, not committed or pushed. The full local
unittest suite subsequently passed **289/289**.

## Why this matters

The transaction engine now exposes `tests_run` and refuses a successful
verdict unless it sees a positive unittest case count. The multi-file
supervisor propagates that count, distinguishes `no_tests` from a normal
test failure, and rejects missing or invalid count receipts.

The count is extracted from unittest's complete stderr output; it is **not
a cryptographically trusted execution attestation**, and malicious code
could forge output. Docker confinement is likewise not a certified
hostile-code sandbox. Continue to restrict test environments and approvals.

## Scope and reproducibility

[Machine-readable outcome and exact input hashes](evidence/v26_zero_unittest_real_issue.json)
record the snapshot, public verifier, after-the-fact verifier, one
model-authored patch and fixed Docker behavior. Recheck the public cases
with:

```bash
python -m unittest discover -s tests -p test_zero_count_public.py -v
python -m unittest discover -s tests -p test_multifile_workflow.py -v
python -m unittest discover -s tests -p test_transactional_patch.py -v
```

This was an **internal real defect repair** with one successful supervised
proposal. It was not an unknown external GitHub issue, a blinded independent
test of model performance, a same-model baseline comparison, or proof that
Nykra increases coding-agent task success rates.
