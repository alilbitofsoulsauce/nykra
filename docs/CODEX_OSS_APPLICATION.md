# Codex for Open Source — Nykra maintainer application notes

Official program and application: https://openai.com/form/codex-for-oss/
Program overview: https://developers.openai.com/community/codex-for-oss

**Eligibility is not guaranteed.** OpenAI evaluates active core maintainers, real project adoption/usage and ecosystem importance. Nykra is a new independent, open-source project; do not fabricate stars, monthly downloads, outside contributors, production usage or a mature security track record. The source presently demonstrates meaningful engineering and reproducible local benchmarks, **not proven overall coding-model effectiveness gains**.

## Project overview for an application

Nykra is a MIT-licensed, local-first, agent-neutral development tool for auditable code exploration and safe patch evaluation. It provides Git patch transactions across allowlisted files, isolated public tests, checked local evaluation receipts and reviewable evidence. It runs with user-controlled providers such as ChatGPT plus Rel.AI rather than requiring a proprietary inference gateway.

Suggested answer to "Why does the repository qualify?" (must remain under the form's 500-character limit; **do not claim external adoption**):

> Nykra is a new MIT-licensed tool for safer, auditable coding-agent workflows. It offers agent-agnostic execution, transactional multi-file Git patch testing, reproducible public-test evidence and exact-input caching. The project is early-stage with documented tests, security boundaries and honest negative benchmark results. I maintain the core code, releases and contributor workflow and aim to make these reusable for OSS maintainers.

Suggested answer to "How would you use API credits?" (only if requesting API credits and able to use them responsibly):

> I would use optional Codex API credits to evaluate coding agents on new, independently tested OSS issues; prototype maintainer-focused PR review, bug triage and regression workflows; compare against no-Codex baselines; and publish reproducible results, including failures. Nykra must remain usable with other agent providers, and API calls will be explicitly opt-in and budgeted.

Suggested optional explanation:

> This is a newly published research/engineering project, so repository adoption and maintainer activity are still developing. I will report metrics transparently and maintain tests, issues, triage and releases. Claims of universal coding-agent performance improvement are not established.

## Application checklist

1. Verify the GitHub repository is **public** and the account's GitHub profile is visible.
2. Link to the actual repository and disclose its real current stars, downloads, outside contributors and usage.
3. Describe your actual role as primary/core maintainer truthfully.
4. Enter your own ChatGPT account email and any OpenAI organization ID requested by the official application. Never commit that ID, billing data or API keys to the repository.
5. Review the official program terms and submit the form yourself. Eligibility and benefits are decided by OpenAI, and application submission is not an automatic acceptance.
6. Maintain real issues, reviews, releases and contributor communications after launch; the GitHub repository itself should demonstrate ongoing OSS stewardship.

## Relevant source references

- README.md and docs/EVIDENCE.md — exact benchmark scope and negative results
- docs/MULTIFILE_TRANSACTION.md — verified two-file engineering problem
- tests/test_transactional_patch.py — test cases and rollback safety
- SECURITY.md and CONTRIBUTING.md — maintenance practice
- .github/workflows/ci.yml — clean-clone package and regression gates

This file is preparation, not proof that an application was submitted.
