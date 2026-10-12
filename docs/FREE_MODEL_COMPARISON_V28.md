# v0.28 development — Live free-model Nykra versus baseline coding trial

## Outcome

**No coding-success uplift: baseline 0/1; Nykra adaptive 0/1.** This is a
real, supervised, matched four-model-call comparison on a historical upstream
feature request, not a benchmark pass or an official leaderboard entry.

For the first time in this feature-branch series, **both arms received their
own independently generated model outputs**, with the same frozen first
prompt, identical model, equal four-call ceiling, public-only feedback and
separate pinned Docker patch evaluations.

| Measured metric | Depth baseline | Nykra adaptive |
| --- | ---: | ---: |
| Real external issue | more-itertools #1134 | Same |
| Model and route | `cohere/north-mini-code:free` | Same |
| Completed model calls | **4** | **4** |
| Distinct generated model contents | 2 | 3 |
| Valid Git diff executions | **3** | **4** |
| Public-passing patches | **0** | **0** |
| Terminal selected patch | None | None |
| Solved tasks | **0/1** | **0/1** |
| Model-reported total tokens | **18,725** | **15,187** |
| Provider-reported inference cost | **$0** | **$0** |

**A real policy decision fork occurred at attempt 4**: depth revised
attempt 3, while Nykra adaptive started a new root. Neither succeeded.
There is no basis to credit adaptive exploration with better coding accuracy.

## Reproducibility

- Upstream issue: [more-itertools #1134](https://github.com/more-itertools/more-itertools/issues/1134),
  a historical feature addition, not an invented bug.
- Feature-absent upstream Git commit:
  `9210d54527ddfa63ebe75cd5b5daa0201902c674`.
  The historical reference implementation is commit
  `18c57c720fc5a7672439ea45a5393a8c1ff40d1e`, **never presented
  to the model**.
- The normalized, clean frozen checkout commit, same for both arms:
  `b1ecd895e2c97928cb53406fe3aa58d1fd923ab4`.
  Only two upstream Python files were converted from CRLF to LF for
  Nykra's patch parser. That change does not affect Python behavior.
- Frozen public tests SHA-256:
  `e882cde666ca3e775e5d8fe02d26af25ec0ea3077d4a8ceef5990cf8a67614b8`.
  Held-out checks SHA-256:
  `7f3edd5ee7eece9531532996e1d198d0cdd5d7caed0862d2c15d84f841a96058`.
- The first request in each arm used the exact same hashed
  [prompt](evidence/v28_northmini/initial_prompt.txt), then received
  only its own public diagnostics. No hidden tests or reference fix
  were included in model prompts.
- Same pinned Docker image and `multi-workflow` Git transactional evaluator
  in both arms, with exactly
  `more_itertools/more.py` and `more_itertools/recipes.py` allowlisted.

The inference adapter is `nykra/free_model_client.py`. It requires
explicit approval, an environment-provided OpenRouter credential, an exact
`provider/model:free` identifier, network provider fallbacks disabled, and
refuses nonzero provider-reported cost. After online troubleshooting,
`reasoning.enabled=false` was selected **before the scored matched study**:
two earlier long-form free requests without this setting had spent their
output budgets on reasoning and returned no code. Those connectivity failures
are not scored as model task failures.

The model authored two clearly delimited *Python source sections* per
proposal. The fixed, deterministic wrapper appended the first section to
`more.py`, added the four named exports to `__all__`, and replaced the
original `running_mean` in `recipes.py`. It did **not** repair semantics.
Tests were executed in Nykra's isolated Docker evaluation, not by executing
free-model source in the user's Windows shell. The entire eight independent
model output files, all prompts, Git diffs, public receipts and finalization
receipts are archived in [v0.28 raw evidence](evidence/v28_northmini/).

## Actual failure sequence

| Model call | Depth baseline | Nykra adaptive |
| --- | --- | --- |
| 1 | Valid two-file diff; 6 public tests ran and failed | Independently generated two-file diff; 6 ran and failed |
| 2 | Repeated attempt-1 output byte-for-byte; failed public again | Repeated its own attempt-1 output byte-for-byte; failed public again |
| 3 | Again repeated its own initial output; failed public | New source output, still failed six public checks |
| 4 | Revised attempt 3 but generated an **incomplete second section**; model-invalid, not submitted for grading | **New-root** independent proposal formed a valid two-file diff; six public tests failed |

Nykra therefore performed **four** public Docker evaluations versus
**three** for baseline, due to the baseline's invalid fourth output.
Neither reached a passing public candidate. As registered in advance,
hidden checks are only applied to a selected public-passing proposal, so
**no hidden tests were run**. It would be false to claim hidden-verified
success or a hidden failure verdict for either model.

The token counts reflect **different model context lengths** after the
fork and the large prior code included in depth revision prompts. They are
descriptive only, not controlled evidence of token or wall-clock savings.
The free endpoint returned zero reported dollar cost for all eight successful
code-returning requests; this does not guarantee permanent zero pricing,
unlimited quotas, or private handling of prompts by the provider.

## Engineering result and limitations

A real free code-generation path works independently of native OpenCode:
`python -m nykra.free_model_client` selects a strict `:free` route, validates
model identity, disables extended reasoning for this adapter, and persists
a candidate only on successful nonempty output. It does not run code or
mutate a Git repository by itself; Nykra's separate allowlisted evaluator
handles submitted diffs. The new focused test suite has **10 isolated tests**
covering approval, pricing guard, model substitution, reasoning-only output,
timeouts, credential requirement, and safe file output.

**Interpretation:** one previously published issue, a small supervisor-authored
public suite, non-blind model sampling, a mechanical patch assembly wrapper,
and no successful solutions. An exercised exploration fork is a necessary
engineering milestone, **not evidence of general or causal accuracy uplift**.
The record includes all failures and duplicate outputs rather than discarding
the unfavorable attempts. No patches were promoted and no Git commit/push was
performed.
