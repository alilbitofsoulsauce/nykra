# v0.29 development — Verified redundant Docker public-evaluation avoidance

Nykra's multi-file workflow now supports **opt-in, within-session reuse of an
already evaluated, byte-identical, failing public-test patch**. This eliminates
repeated disposable Git checkout and Docker grading when an external coding
model keeps returning the same bad code.

**Measured engineering result: 7 actual Docker evaluations without reuse versus
4 with reuse — 3/7 avoided (42.86%) — with unchanged attempt counts, controller
actions, and unsuccessful task outcomes.** This is not a coding-accuracy gain.

## Why

In the preceding real-model v0.28 experiment, the free coding model independently
produced four responses per arm but repeated exact code: depth's patch sequence
was A/A/A (then an incomplete fourth output); adaptive's sequence was A/A/B/C.
Across the **seven valid public evaluations**, three repeated work. The new
capability uses exactly that *duplication pattern*, not historical test outputs,
in a fresh synthetic two-module repo to test what can actually be avoided.

## How to use

Start an ordinary multi-file session with an additional flag:

~~~sh
python -m nykra multi-workflow start --repository /path/to/clean/repo \
  --task "Fix two interacting modules" \
  --allow engine/calc.py --allow engine/routes.py \
  --policy adaptive --budget 4 --dedupe-public \
  --test-target tests.test_invoice \
  --docker-image-id sha256:YOUR_PINNED_IMAGE_ID --approve
~~~

Continue using `multi-workflow next`, `submit`, `summary` and
`finalize` normally. Repeated proposals **still consume an attempt**
and are separately archived with distinct attempt IDs, parent IDs and patch
files. An eligible receipt has `public_test_reused: true`,
`reused_from_attempt_id: "attempt-1"` and
`public_tests_executed_now: 0`. `tests_run` retains the original
public-test case count, with the reuse flag distinguishing replay from execution.
The `public_work` counters separate real evaluator calls from reuses.

The default is **OFF**. The workflow only reuses within the *same approved
session*. It rechecks the source Git HEAD and refuses dirty repositories,
parses the repeated Git patch against the same path allowlist, and reads back
the original saved patch file to compare exact bytes (not just a hash).
It does **not** reuse infrastructure errors, untested or malformed patches,
a purported success, or an unrecognized original patch file. A missing or
tampered receipt falls back to real evaluation. The existing file locks and
explicit approval remain in force; no source is promoted or published.

## Actual pinned-Docker A/B fixture replay

The [raw machine receipt](evidence/v29_multifile_dedupe_docker.json) was
produced by a reproducible, approval-gated command:

~~~sh
python -m scripts.measure_multifile_dedupe \
  --image sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f \
  --output /path/to/new-replay.json --approve
~~~

The local Docker image must already exist. The script only constructs an
ephemeral synthetic Git fixture with two defective modules, three deliberately
failing two-module diffs, and a tiny two-case Python `unittest` suite. It
runs all four sessions with the **same pinned Docker image, public target,
three/four patch submissions, and policies**. The experiment is deterministic
in patch content but Docker wall time varies with startup and host load.

| Path | Public submissions | Real Docker evaluations | Reused verdicts | Observed submit wall time |
| --- | ---: | ---: | ---: | ---: |
| Depth without reuse | 3 | 3 | 0 | 6.5852 s |
| Depth with reuse | 3 | 1 | 2 | 2.1361 s |
| Adaptive with reuse | 4 | 3 | 1 | 6.5878 s |
| Adaptive without reuse | 4 | 4 | 0 | 8.1188 s |
| **Total, without reuse** | **7** | **7** | **0** | **14.7040 s** |
| **Total, with reuse** | **7** | **4** | **3** | **8.7239 s** |

These measured times are **not a general speedup estimate**: the four
sessions were run sequentially and have warm/cold Docker and Windows cache
effects. The robust, deterministic accounting is **seven real evaluations
versus four**; all fourteen A/B submissions recorded the same failed test
outcomes, and the adaptive controller still started a new root on its final
proposal. **No LLM calls occurred in this replay**, so claims about provider
token or model cost savings do not follow from these measurements.

## Regression gates

The multi-file workflow suite checks real Git operations, default-off mode,
correct reuse provenance, attempt budget preservation, clean-HEAD rejection,
new distinct proposals, saved-patch tampering, invalid patches, simulated
Docker receipts, zero-discovered-test cases and cross-process settings.
The separate [replay evidence test](../tests/test_multifile_dedupe_evidence.py)
verifies the saved Docker counts and unchanged policy decisions without
starting Docker in CI.

~~~sh
python -m unittest discover -s tests -p test_multifile_workflow.py -v
python -m unittest discover -s tests -p test_multifile_dedupe_evidence.py -v
~~~

**Boundaries:** This only saves duplicate public evaluation work. A failing
model may still consume its entire proposal/token budget. Do not enable
same-result replay for nondeterministic/flaky public tests or tests whose
results depend on conditions outside the pinned clean Git tree and runner
configuration. Per-user session records are not tamper-proof against the
machine owner, and the Docker environment is not a certified security
sandbox. One synthetic A/B replay does not establish a generalized latency
improvement or better coding-agent completion rates.
