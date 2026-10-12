# v0.30 development — Stop redundant inference before requesting the model

Two separate, **explicitly opt-in** controls help Nykra spend less inference
effort without misrepresenting repeated text as progress.

## 1. Exact authenticated inference-request reuse

The free endpoint adapter `nykra/free_model_client.py` now accepts:

~~~sh
python -m nykra.free_model_client \
  --model cohere/north-mini-code:free \
  --prompt-file first_request.txt \
  --output-file first_proposal.txt \
  --max-tokens 450 --timeout 45 \
  --cache-dir /your/private/nykra-inference-cache \
  --reuse-exact-request --approve
~~~

For the **same exact prompt, API account, model, token limit and request
settings**, run the same command with a *different* output file name. A saved,
authenticated successful free response is returned **before contacting the
provider**. Both `--cache-dir` and `--reuse-exact-request` must be given.
If either is absent, the old one-call/no-cache behavior remains the default.

The request fingerprint is a SHA-256 HMAC, keyed using the API credential and
covering the entire exact prompt, endpoint, model and wire generation settings.
The credential and raw prompt are **not persisted**; the complete
**model-generated output is persisted**, and should be treated as confidential.
The cache directory is operator-selected; on Unix it must have private owner
permissions. The cached text and original receipt are integrity-signed by HMAC
and byte-hashed. Tampered/malformed entries stop without falling back silently
to a new provider call. Provider-reported unknown or nonzero cost is never
cached as a verified free result. Cross-account credentials have different
cache keys, and concurrent executions use a local lock. The user controls the
cache directory and retention.

Receipts distinguish origin versus current request:

- `cache_hit: true` and `provider_called_this_request: false` mean no new
  model completion was requested.
- `provider_tokens_this_request: 0` and `cost_this_request: 0` are measured
  by the **absence of an API call**. The existing `tokens`, `response_id`
  and `elapsed_seconds` fields belong to the original provider result and
  must not be interpreted as this cache hit's consumption or latency.
- A fresh successful request may produce `cache_hit: false` and
  `cache_saved: true` when the provider explicitly reports `cost: 0`.

### Live authenticated free-model measurement

On October 12, 2026, the workstation made three identical real coding
requests to `cohere/north-mini-code:free`. The first genuinely contacted
OpenRouter and returned 38 characters of Python code. The second and third
were returned from the cache with the same SHA-256 output fingerprint.

| Measure | Live observed value |
| --- | ---: |
| Submitted identical requests | **3** |
| Actual authenticated provider calls | **1** |
| Provider calls avoided | **2 (66.67%)** |
| Provider-reported tokens on actual call | **32** |
| New provider tokens on both cache hits | **0** |
| Provider-reported cost on actual call | **$0** |
| Distinct SHA-256 output fingerprints | **1** |

[Machine-readable live receipt](evidence/v30_live_exact_request_reuse.json).
The receipt deliberately omits the prompt body, source code, API credential
and local cache path. Live-run source and output remained on the local
workstation. The reproducible opt-in script
`python -m scripts.measure_free_request_reuse --model MODEL --prompt-file
PROMPT --cache-dir PRIVATE --output NEW_JSON --requests 3 --approve`
provides a reusable benchmark that saves only non-secret hashes and receipts.

**This was a deliberately identical request replay, not three different
coding challenges.** The avoided-call fraction is meaningful for that replay
only. In v0.28, revision prompts were all different, even when the provider
later returned duplicate code, so this request cache by itself would have
saved **zero v0.28 inference calls**. The cache cannot predict whether
different prompts will return the same code, and it cannot make a model
more accurate.

## 2. Optional repeated failed-patch guard for external agents

The multi-file workflow has a second, independent safety/economy option:

~~~sh
python -m nykra multi-workflow start \
  --repository /clean/committed/repo --task "Fix two interacting modules" \
  --allow engine/calc.py --allow engine/routes.py \
  --policy adaptive --budget 4 \
  --docker-image-id sha256:YOUR_PINNED_IMAGE_ID \
  --halt-on-repeat-failure --approve
~~~

If **two consecutive submitted patch attempts have identical fingerprints
and recorded failing public outcomes** (including a legitimately reused
public verdict for the second), the next request does not ask for another
model completion. It instead returns
`status: paused_repeated_failed_patch`,
`agent_required: false`, `model_invocation: false`, and the unspent attempt
budget. The session is deliberately blocked from further submissions,
but may be finalized/aborted. An operator can begin a *new* approved session
with different prompts, policy or model.

This is an **early-stop policy, not a model-output prediction**. It is
default-off because an agent could have solved the task on the next call.
For example, applying the guard retrospectively to v0.28's two equal
first-patch failures would prevent both arms' third and fourth calls, but
also prevent Nykra's independent fourth-root exploration. Those calls were
*not* actually avoided in the historical v0.28 live study, so they are
**not included** in the real savings above. The code preserves all observed
attempts, original public-test outcomes, source Git protections and explicit
approval. Using it may **decrease task success** on recoverable failures.

The previous `--dedupe-public` option remains separate: it avoids redundant
Git/Docker public tests *after* a model proposal exists. With both opt-ins
enabled, an identical failed second proposal can reuse the test receipt,
then halt new inference requests before a third call; it does not refund
the first two model calls.

## Validation and limits

Run the offline, zero-cost tests:

~~~sh
python -m unittest discover -s tests -p test_free_request_cache.py -v
python -m unittest discover -s tests -p test_multifile_workflow.py -v
python -m unittest discover -s tests -p test_live_exact_request_evidence.py -v
~~~

There is no new claim of coding success or adaptive-policy win. Saved prompts
are not shared across providers; only the validated free-route adapter
currently implements inference caching. A cache hit replays the *same*
original source even if the provider would now generate something different;
leave this feature disabled when fresh stochastic completions are desired.
The early-stop guard is an alternative to continuing exploration, not a
replacement for controlled coding benchmarks. Never use these results to
claim Nykra improves model intelligence or accuracy.
