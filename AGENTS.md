# Nykra repository instructions for coding agents

This repository develops local-first, agent-neutral exploration evidence, replay and safe patch evaluation. Do not claim that Nykra improves model coding accuracy without independent task-level evidence.

Workflows:
- Inspect README.md, docs/EVIDENCE.md, docs/MULTIFILE_TRANSACTION.md and relevant source/test modules before editing.
- Use the current user-authorized workstation/Rel.AI host; do not silently invoke paid model APIs or install agent providers.
- Never execute untrusted tests in the local host. Prefer the pinned constrained Docker executor, but do not assume it is a perfect security boundary.
- Require the user's approval to promote, commit, push or publish. Preserve all existing evidence and negative results.
- Changes should be reversible and made in a disposable checkout; use precise path allowlists.
- Small tests: python -m unittest discover -s tests -p test_transactional_patch.py -v
- Smoke: python -m nykra demo
- Full historical tests require provisioned ignored external benchmark sources and Docker; they are not guaranteed to run on a clean clone.
- Do not modify docs/evidence historical results to make a claim look more favorable.
- Never stage experiments/, .env files, tokens, private credentials, virtual environments, dist/, build/ or local runtime history.
- Prefer new focused tests, tight security boundaries, and clearly documented limitations.
