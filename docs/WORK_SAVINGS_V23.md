# Nykra v0.23 — Measured real Git/Docker work reduction

## Demonstrated benefit

**Nykra now avoids repeating identical verified public work across agent branches.** When two authorized coding-agent sessions propose the **same source for the same registered task, evaluator, parent history and pending prompt**, the first session genuinely applies the patch in a disposable upstream Git checkout and runs the constrained Docker public regression. The second receives a verified local receipt, without running the same Git patch/Docker regression a second time. Final hidden evaluation remains independent.

This optimization uses no paid Codex model call; it operates with **ChatGPT authoring proposals and Rel.AI supervising the workstation**, and also accepts proposals from any agent via the JSON workflow. It does **not** provide its own standalone model inference or replace ChatGPT's conversation usage limits.

### Frozen real-work controlled replay

Before performance testing, [v0.23 protocol](evidence/v23_reuse_protocol.json) froze the two original v0.22 BugsInPy upstream issues, archival Git patch/source hashes, test protocol, order, success criteria and the measurement method. We deliberately chose previously used issues **as an engineering performance replay**, not new coding-ability evidence.

The exact same earlier genuine Codex-generated function sources were replayed—**without any new model-generation calls**—in two modes:

- **Ordinary:** both matched policy sessions independently apply their Git patches and run the public Docker tests, as the v0.22 system did.
- **Nykra shared:** the first session applies and tests once; if the second has the exact same candidate history, model-facing prompt and action, it inherits the verified public receipt. When the policies diverge, both branches again apply and test independently.

Both conditions still run the separate hidden verifier for publicly solved cases. The order was alternated by issue to reduce, not eliminate, environment-warming bias.

| Real upstream issue | Ordinary public Docker runs | Nykra public Docker runs | Ordinary elapsed | Nykra elapsed | Final result in both modes |
| --- | ---: | ---: | ---: | ---: | --- |
| youtube-dl bug 27 | 8 | 5 | 79.5442 s | 41.9019 s | Both policies fail |
| youtube-dl bug 43 | 6 | 3 | 42.4337 s | 28.7508 s | Both policies pass hidden tests |
| **Total** | **14** | **8** | **121.9779 s** | **70.6527 s** | **Unchanged** |

**Verified infrastructure savings:** 6 fewer **real Git patch applications** and 6 fewer **real public Docker runs**, reducing both by **42.9%**. **Observed elapsed reduction:** **51.3252 seconds (42.1%)** across these two one-time local replays. No additional Codex, other model, or token-billed API call was made during the replays.

These figures come from [machine audited summary](evidence/v23_reuse_summary.json), [bug 27 run](evidence/v23_reuse_youtube_dl_27.json), [bug 43 run](evidence/v23_reuse_youtube_dl_43.json), and the SHA-256 [portable source/patch/session export](evidence/v23_session_export_index.json).

**Interpretation:** Nykra demonstrably saves real Git/Docker evaluation work when requests are **identical**; it does **not** demonstrate that Nykra writes better code, improves pass rates, or runs 42% faster on general tasks. The two cases were historically reused and do not establish statistical performance distributions. The elapsed measurements include host overhead and uncontrolled cache/warm-up effects; the **6 avoided executions** are the reproducible mechanistic benefit.

## Security and correctness conditions

Reuse is explicitly authorized and fails closed unless all of the following match:

1. A valid Nykra-owned source and target session and the same preregistered real Git task, pinned evaluator protocol and public feedback configuration.
2. Matching earlier candidate ancestry, action/parent IDs, exact prompt SHA and source SHA.
3. Original source contains an **actually applied and publicly graded Git patch**, with its exact patch bytes present and hash-verified, from the pinned buggy upstream revision.
4. Source public outcome is `ok` or `test_failed`; **never reuse** evaluator failures, unsigned guesses or a receipt copied from another receipt.
5. The new target session is unmodified and waiting for that exact action, and no hidden test verdict is copied into its model-facing prompt.

A matching source still produces a **separate immutable target patch copy** and full source/patch ancestry for audit. Each completed policy session independently runs its final hidden check; correct fixes remain correct and failed fixes remain failures. This is **trusted-local-session reuse**, not a cryptographic guarantee against an adversary who can edit all host session files; it is not a certified hostile-code sandbox.

## Rel.AI / ChatGPT usage without Codex

Nykra still supports supervised, portable agent turns:

```bash
python -m nykra workflow tasks
python -m nykra workflow start --task youtube-dl-43 --policy adaptive --budget 4 --approve
python -m nykra workflow next --session SESSION_ID
python -m nykra workflow submit --session SESSION_ID --candidate-file proposal.py --approve
```

When a second authorized session asks for **the identical candidate/parent/prompt**, reuse the previously evaluated source:

```bash
python -m nykra workflow reuse --session TARGET_SESSION --verified-session SOURCE_SESSION --approve
```

This command does **not** call any model, Git apply or public Docker test. It returns the verified status, source/patch hashes, zero additional model/evaluator calls, and the next required agent prompt. If the sessions differ, it **refuses reuse**; generate and test a separate candidate normally. Then finalize each session normally to run hidden checks.

The [independent-process CLI reference check](evidence/v23_cli_reuse_control.json) executed `start → reuse → finalize` using a **previously graded upstream reference fix**, with **zero new public Docker runs, zero new Git applies, zero new model calls**, and a passing independent hidden check. That CLI success is **not a model-generated repair** and is not included in the timing benchmark.

For automatic shared-prefix orchestration via a model/proposal callback, `nykra/v23_paired.py` implements `run_pair(task_id, propose, approve=True)`. Rel.AI/ChatGPT provides the proposal callback or candidate file: Nykra never secretly invokes Codex, an API key, or a separate model provider in this path. It makes one proposal per identical branch decision, tests it once, reuses the result for the other branch, and independently evaluates divergent branch proposals.

## Where this does and does not help

**Useful now:** Multiple agent branches on the same issue, repeated attempts/candidates from the same parent, controlled A/B experiments, paired reviews of identical patches, or a repeated local evaluation accidentally scheduled twice. The savings apply **only at exact shared-history points**.

**Not established:** universal 42% speedup, generalized code repair gains, lower ChatGPT token usage, arbitrary multi-file repositories or concurrency-safe reuse among hostile/untrusted host processes. One unrelated agent task sees **no reuse benefit** if no second matching request exists.

**Next research:** Integrate a bounded content-addressed cache for other strictly identical authorized evaluations; expand beyond one-function patches, with opt-in repository permissions and robust container isolation; test whether better exploration decisions improve end-to-end correctness on genuinely new tasks and other provider runtimes.

**Release status:** v0.23 is implemented in the Nykra source tree, not in the separately installed v0.16.0 passive observer. No Git commit, push, background agent model job, or user repository modification was performed.
