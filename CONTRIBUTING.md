# Contributing to Nykra

Thank you for helping build a local-first, agent-agnostic evidence and coding-workflow tool.

## Before opening a pull request

1. Open an issue describing the bug or feature and why it matters. Small fixes may be submitted directly.
2. Fork and clone Nykra. Python 3.10 or later and Git are required. Docker is optional unless running historical isolated Git issue benchmarks.
3. Create a feature branch from main; keep changes focused, testable and free of credentials, private user files and local model state.
4. Run the dependency-free smoke and the relevant tests:

~~~bash
python -m pip install -e .
python -m compileall -q nykra tests examples
python -m nykra demo
python -m unittest discover -s tests -p test_transactional_patch.py -v
~~~

The complete historical trial suite is not self-contained: it relies on older upstream Git issue sources and a pinned Docker image in ignored local experiments. A clean clone must not need those assets to use Nykra's core and transactional patch functionality. See docs/MULTIFILE_TRANSACTION.md.

5. Include a meaningful regression test and update relevant docs. If changing evaluation policy or benchmark design, register the protocol before measuring model outcomes. Keep all negative results and limitations.
6. Open a pull request with purpose, changed files, exact test commands and results, backward compatibility and security considerations.

## Design and ethics

- Do not conflate a successful synthetic test with general agent improvement. Historical benchmark results are task-specific and may be contaminated by model training.
- Never silently invoke a paid model endpoint. Agent providers are explicit and owned by the user.
- Never print secrets, private files, untrusted external code or full conversation logs into public evidence.
- Prefer dependency-free components. New required dependencies need a strong explanation.
- Agent-generated changes must be reviewed and tested in disposable checkouts before promotion.
- No unrelated commits or force pushes. Changes to user repositories require approval.

## Release and security

Review SECURITY.md before reporting vulnerabilities. Releases require passing the hermetic CI gate and a fresh-clone check. Tracked evidence must remain reproducible and its checksum manifest updated. Maintainers may request changes to tests, threat models or claims before merging.
