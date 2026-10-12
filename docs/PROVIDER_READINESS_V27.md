# v0.27 development: Provider readiness before agent comparisons

Nykra's historical external issue #1134 comparison in v0.26 was a **tie** with a single shared ChatGPT proposal. To improve evidence quality, the next trial froze two *separate* model sessions (depth baseline and adaptive Nykra) on the same clean Git revision and existing public and withheld tests, with four proposals available to each arm.

## Outcome: infrastructure exclusion, not a benchmark loss

**No independent coding proposal was successfully returned.** The configured free backends showed the following behavior:

| Inference route | Observed outcome |
| --- | --- |
| OpenCode CLI 1.4.3, MiMo free | No output before ~86-second timeout |
| OpenCode CLI 1.4.3, Ling free | No output before ~42-second timeout |
| Isolated npm OpenCode 1.19.0 | Installation timed out at 120 seconds; partial executables unusable |
| OpenCode Zen free direct HTTP | Rejected with HTTP 403; free-tier requests must originate inside OpenCode |
| OpenRouter Nemotron 3 Super free, `READY` probe | HTTP 200; exact response `READY`; provider-reported cost $0, ~2.31 seconds |
| Same OpenRouter model, full multi-file coding prompt | No completed model response before the 110-second execution deadline |
| OpenRouter Nemotron 3.5 Lightning free, 90-token probe | HTTP 200; no text output, all 90 completion tokens reported as reasoning; cost $0 |

Both frozen Nykra `multi-workflow` sessions were checked for attempts: **0/4 attempts had been scored** in each. Both sessions were then aborted. No candidate was submitted to the public Docker tester and no hidden tests were disclosed or run for this unsuccessful trial. **Do not put 0/1 or 1/1 in the comparison ledger**: there were zero eligible model-supplied coding results.

The frozen benchmark input hashes, session identifiers, durations and excluded-infrastructure observations are in [the machine-readable record](evidence/v27_free_provider_readiness.json). No private API key or credential value is retained in the record.

## New operational capability

A reusable provider-neutral CLI readiness probe was implemented:

```sh
python -m nykra provider-probe --expect READY --timeout 20 --runs 2 --approve -- <trusted-provider-cli> <arguments>
```

It launches only the **explicit** command supplied by the operator, with `shell=False`, a bounded time limit, and no access to hidden tests. Results indicate a real output match, empty response, unexpected response, subprocess failure, or timeout. Only hashes and lengths of standard output/error are recorded, never their raw contents, because CLIs may print keys, prompts or private source. It does **not** load API keys, choose providers, perform unauthenticated model inference, prove that a backend is free, or automatically spend tokens.

Reproduction of the independent local fixture tests:

```sh
python -m unittest discover -s tests -p test_provider_preflight.py -v
```

These tests exercise real Python subprocess responses, nonzero exits, output redaction, wrong/empty output, permissions, bounded run counts, and deadline behavior. They are not an inference benchmark. Launching arbitrary third-party commands on the workstation remains the operator's responsibility; the timeout stops the direct process but is not a hardened descendant-process sandbox.

**Next research gate:** obtain a native free provider that consistently returns nonempty code at a sufficient output budget, verify repeated paid-free receipts, then rerun this frozen issue with independently produced proposals and unbiased terminal evaluation. If a policy fork never occurs, report the tie instead of attributing randomness to the adaptive controller.
