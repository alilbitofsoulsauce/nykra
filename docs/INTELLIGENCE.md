# Nykra v0.6 — Supervised exploration and policy assessment

Nykra now has a limited but working **supervised exploration controller** and **task-disjoint retrospective policy assessor**. It does not yet autonomously optimize an arbitrary ChatGPT, Cursor, or Rel.AI agent. Passive tool-completion events and editor saves remain observations, not objective results.

## 1. A host creates and evaluates candidates

A trusted host application imports the standard-library-only Nykra API. Example:

```python
from nykra.controller import Proposal, SupervisedController
from nykra.evaluation import EvaluatorResult
from nykra.store import HistoryStore

store = HistoryStore()

def propose(observed, remaining):
    if not observed:
        return Proposal(candidate=5)
    if len(observed) == 1:
        return Proposal(candidate=7, parent_id=observed[0].attempt_id)
    return None

def evaluate(candidate):
    # Replace with a real, fixed, independently checked metric.
    return EvaluatorResult(score=float(candidate), cost_units=1.0)

controller = SupervisedController(
    store,
    evaluator_id="verified-benchmark-v1",
    propose=propose,
    evaluate=evaluate,
    max_attempts=4,
    max_seconds=60,
    approval=True,  # explicitly supplied by the trusted host
)
result = controller.run(task="Example search task", agent="trusted-host")
print(result["run_id"])
```

The proposer receives **only an immutable tuple of measured observations and the remaining attempt count**. It can suggest a root candidate or branch from an observed parent. Nykra validates parent references before calling the evaluator. The evaluated score, status, duration and cost are stored; **candidate objects are never persisted** by Nykra. A parent is an evaluated candidate within the same run. A failure is recorded without storing exception details or raw prompts.

This interface invokes **caller-provided Python callbacks in the caller's process**. It is not a security sandbox: a malicious or indefinitely blocking callback must be isolated and stopped by the *host* (for example, with process/container timeouts, resource budgets and workspace authorization). Nykra's attempt and elapsed-time budgets are cooperative; they are checked between calls. Never attach an arbitrary shell executor, network agent or privileged tool to this interface without host-side permission and safety controls.

Calling with `approval=False` refuses execution before creating a run or invoking callbacks. Nykra does not install this controller into live Rel.AI or coding agents automatically.

## 2. Assess policies retrospectively

After multiple independently named tasks have **genuine evaluator-backed** candidate trees, run:

```powershell
python -m nykra assess --evaluator verified-benchmark-v1 --objective maximize --budget 2
```

The assessment:

1. Filters to **one evaluator version and one objective direction**, excluding runs lacking enough attempts or quality measurements.
2. Excludes duplicate task labels entirely rather than letting repeated runs of the same task leak across training and held-out groups.
3. Splits tasks deterministically using a SHA-256 hash; all policy choices are made **only** from the training group.
4. Compares breadth-first (fixed baseline), depth-first and a simple adaptive heuristic on *the same recorded outcomes* at a fixed attempt budget.
5. Converts measured best scores into per-task `[0,1]` utilities based on each completed recorded tree's valid score range. This scale is retrospective and **is not used by the decision policy**. When a policy sees no successful score its utility is zero.
6. Requires at least eight distinct training tasks and eight held-out tasks by default, positive training lift, positive held-out mean lift, at least eight held-out non-tied paired differences, and a one-sided exact sign-test p-value no greater than 0.05.

If this evidence is inadequate, Nykra returns `insufficient_evidence` or `hold_baseline` without a recommendation. If the gate passes it returns `advisory_candidate` and a policy name, **never automatic activation**. The response always carries `can_auto_apply: false` and `agent_policy_modified: false`.

The sign-test gate is a conservative exploratory filter, not a license to announce a statistically proven deployment gain; assumptions of task independence and unbiased sampling still matter. Historical replay can change selection order among candidates that were actually evaluated, but **cannot predict unseen actions**, reproduce a different live search trajectory, or prove a causal improvement. Dataset/task selection and the originally collected search tree can bias offline comparisons.

## 3. Reproducible synthetic demonstration

```powershell
python -m nykra intelligence-demo
python -m examples.intelligence_demo
```

The demonstration generates 60 artificial tasks, creates actual evaluated candidate branches through the controller, splits tasks into training and held-out sets, and runs the policy assessor. The data and rewards are **synthetic and deliberately structured** to show how the comparison works. No real model API, prompts, network service or workstation agent is involved, and the fixture lives in a disposable temporary history database.

This is a *correctness/behavior test* of the control and assessment code. It is not evidence that depth or adaptive exploration will outperform breadth on your actual workloads.

## 4. What still requires a real agent-runtime bridge

- An authorized host must own candidate generation, evaluator identity, objective consistency, workspace snapshotting, task isolation and execution approvals.
- Current passive Rel.AI history and IDE events do not supply branch ancestry or trustworthy objective scores.
- Nykra does **not** currently inject recommendations into a live model prompt, replace another agent's exploration strategy, tune model weights or run unattended optimizations.
- A future prospective experiment must compare assigned policies across newly encountered tasks using comparable budgets, actual outcomes, logged failures and explicit approval before gradual rollout.

For future integration, use `SupervisedController` in the **authorized execution supervisor**, not a new tool that each individual agent must call. Host authors should keep model/tool inputs and credentials out of Nykra's persisted metadata.
