# Nykra v0.9 — Supervised coding agents using Rel.AI

The integration path is ChatGPT → existing Rel.AI MCP tools → Nykra coding supervisor → isolated Python candidate evaluation. Nykra does not require agyc, patch the Rel.AI desktop application, or add an agent-facing MCP tool.

An AI agent authors candidate source files, and an authorized host invokes Nykra through the existing Rel.AI execution tool. The candidate Python code really executes; the host computes independent expected results and stores measured scores. The agent must still propose candidate implementations. Nykra does not control the model's hidden reasoning or call a model automatically.

## Tasks and standalone evaluation

Run:

    python -m nykra coding tasks

Available fixtures: unique-sorted, balanced-brackets, and merge-intervals. Each task expects one function named solve. The subprocess worker rejects imports, attribute access, unsafe calls, module-level side effects, and unsupported syntax. It allows a small set of built-in functions. This AST restriction plus a subprocess timeout is defense in depth, NOT a hardened sandbox against malicious code.

A trusted agent can test a proposed function from a file:

    python -m nykra coding evaluate --task unique-sorted --candidate-file candidate.py --approve

Nykra generates input cases independently, sends only the candidate source and inputs to the worker, collects outputs, and compares outputs against expected results outside the worker. Different training and held-out inputs are used. These fixtures are public within the repository and do not count as blind third-party coding benchmarks.

## Prospective task integration

An AI agent writes a JSON candidate pool. Example:

~~~json
{
  "task_id": "unique-sorted",
  "proposals": [
    {"id":"root-a","parent_id":null,"source":"def solve(values):\n    return sorted(values)\n"},
    {"id":"fix-a","parent_id":"root-a","source":"def solve(values):\n    return sorted(set(values))\n"},
    {"id":"root-b","parent_id":null,"source":"def solve(values):\n    return list(set(values))\n"}
  ]
}
~~~

Candidate parents must precede their children. Nykra validates the complete pool before assigning the task. The caller requests a prospective trial with fixed objective, policy, evaluator, time and attempt budgets:

    python -m nykra prospective create --evaluator nykra-coding-fixtures-v1 --objective maximize --threshold 1.0 --challenger depth --attempt-budget 2 --seconds-budget 30 --max-tasks 40 --min-per-arm 10 --approve

Then it invokes:

    python -m nykra coding trial --trial TRIAL_ID --task-key UNIQUE_TASK_IDENTIFIER --pool-file proposals.json --approve

The experiment saves a randomized policy assignment before evaluating the agent's candidates. Nykra actually traverses the candidate tree under that policy and tests only the selected proposals, using scores revealed so far. It saves scored attempts and sanitized parent-child links in the Nykra history store, and the final held-out score in the prospective trial. Candidate source strings are not saved in the Nykra databases, although the caller's original proposal file remains on disk until explicitly deleted.

The result is an executed, policy-governed model-authored coding task, NOT automatic LLM exploration control. No live model policies are modified.

## Actual Rel.AI smoke experiment — October 11, 2026

Using this ChatGPT session and the connected Rel.AI MCP tools, the assistant authored proposals for three different coding problems and ran them on the workstation. Their independent held-out test scores were:

- unique-sorted: 0.59375
- balanced-brackets: 0.875
- merge-intervals: 0.375

All three were randomly assigned breadth-first search with a two-candidate budget. None reached the predetermined passing threshold of 1.0. The trial was closed with three breadth assignments and zero depth assignments, so the result is NOT statistically conclusive and the trial remains not_ready for policy comparison. Nykra retains the measured run records, while temporary candidate proposal files can be removed.

The agyc CLI remains untouched: its launcher points to a missing package entry point, but Rel.AI is sufficient for this supervised workflow. There is no assertion that the opaque Rel.AI model internals were controlled.

## Boundaries

Code execution occurs in a short-lived subprocess, isolated Python mode, limited environment variables and short timeouts. This is not container-level isolation or a secure sandbox against deliberately malicious code. Source files and test fixtures are authored or visible within the environment. The pool is agent-generated and the selected policy can only select among proposals already provided by that agent, so this approach cannot fairly compare wholly different live model search strategies without a more capable model-runner integration.

The three included fixtures are demonstrations, not a sufficiently broad benchmark. Future improvements require new independent tasks, controlled prompt and candidate-generation budgets, isolation of repository snapshots, and supported model invocation hooks. Advisory gates never auto-apply a policy.
