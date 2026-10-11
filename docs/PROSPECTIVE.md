# Nykra v0.7 — Prospective Agent Policy Experiments

Nykra v0.7 adds **opt-in, prospectively assigned A/B policy experiments** for trusted agent-execution hosts. It is **not automatically attached to ChatGPT, Rel.AI, Cursor, or Windsurf**. The existing read-only Windows observer continues to collect passive events, but passive events remain unscored and are not eligible for prospective results.

Unlike the v0.6 replay assessor, this protocol allocates a **policy before** a new task begins. A trusted host must actually execute the assigned policy and use an independent, fixed evaluator to score the completed task.

## What is predeclared?

A new trial fixes the baseline policy (`breadth`), challenger (`depth` or `adaptive`), evaluator version, objective (`maximize` or `minimize`), threshold for task success, maximum candidate attempts, seconds budget, maximum tasks, minimum arm sizes, and minimum effect.

Assignment uses the Python cryptographic random generator to allocate each distinct task to either arm. The assignment is saved in a dedicated SQLite database **before** the host sees it. Repeated requests for the same task return the same assignment, even after process restarts. Task keys are represented in the database using an experiment-specific keyed hash; the original task text, prompts, tool arguments, result contents and candidate payloads are never persisted.

In the repository, a synthetic, isolated demonstration is available:

```powershell
python -m nykra prospective-demo
```

It uses intentionally different manufactured outcomes by arm and **must not be interpreted as a real-agent improvement measurement**.

## Host API

```python
from nykra.evaluation import EvaluatorResult
from nykra.prospective import ExecutionResult, ProspectiveExperiment
from nykra.store import HistoryStore

protocol = ProspectiveExperiment(HistoryStore())

trial = protocol.create(
    evaluator_id="independent-tests-v1",
    objective="maximize",
    threshold=0.8,             # fixed before any task assignment
    challenger="adaptive",
    attempt_budget=6,
    seconds_budget=120,
    max_tasks=100,
    min_per_arm=20,
    min_effect=0.05,
    approval=True,             # authorized supervisor opted in
)

def execute(policy, task, max_attempts, max_seconds):
    # YOUR authorized host must ACTUALLY use policy and enforce these limits.
    # Return the candidate, host-measured attempts and cost.
    raise NotImplementedError("Connect to a trusted agent executor")

def evaluate(task, candidate):
    # YOUR fixed independent evaluator—not an agent self-rating.
    raise NotImplementedError("Run authoritative tests or benchmark")

# Invoke only after implementing authorized execution and evaluation:
# result = protocol.run_task(
#     trial_id=trial["id"], task_key="new-task-001", task=your_task,
#     execute=execute, evaluate=evaluate, approval=True)
```

The trial is deliberately not able to spawn commands, change model policies or inject prompts itself. These are **trusted host callbacks**, not secure sandboxes. Nykra checks attempt and wall-time budgets after a callback returns; a hanging or malicious callback must be terminated by the host's own isolated process/container controller.

Exceptions raised by either callback are recorded as failures without persisting the exception message. Budget and time violations count as unsuccessful assignments, **not as excluded or silently dropped results**.

## CLI protocol for a supervised external host

When an authorized supervisor wants to manage assignments manually:

```powershell
python -m nykra prospective create --evaluator independent-tests-v1 --objective maximize --threshold 0.8 --challenger adaptive --approve
python -m nykra prospective assign --trial TRIAL_ID --task-key task-001
python -m nykra prospective claim --trial TRIAL_ID --assignment ASSIGNMENT_ID
```

The host must then execute the returned policy (and enforce the returned budgets) and use its independent evaluator before submitting the outcome:

```powershell
python -m nykra prospective finish --trial TRIAL_ID --assignment ASSIGNMENT_ID --status completed --score 0.92 --attempts-used 3 --cost 1 --elapsed-ms 8500
```

A task that failed or crashed should be explicitly finalized using `--status failed` and **must not be omitted**. For over-budget execution, use `budget_violation` or `timeout_violation`. Only `completed` outcomes with an independently supplied score are eligible to pass the threshold.

When the predefined intake period is over, all assigned tasks must have terminal outcomes before closing:

```powershell
python -m nykra prospective close --trial TRIAL_ID
python -m nykra prospective report --trial TRIAL_ID
```

The CLI does **not** verify that a human operator's submitted score actually came from tests. The trust boundary remains the authorized host; production evidence requires an auditable evaluator and enforcement of trial budgets.

## Reporting and recommendation gate

Each arm shows assigned count, finalized count, unsuccessful and violated assignments, intent-to-treat success rate, a Wilson binomial interval, and the mean measured score for *evaluated* tasks as secondary descriptive information. The **primary outcome** is the predefined threshold pass/fail.

When the trial is still open, has pending tasks, or either arm has fewer than the prespecified minimum, Nykra returns `not_ready` and **does not compute the final significance statistic**. After it is closed and sufficiently complete, it calculates the challenger minus baseline success-rate difference and the one-sided Fisher exact p-value. The gate requires **p ≤ 0.05 and observed improvement at least the fixed minimum effect**.

Passing this gate yields `advisory_candidate`, *not* an automatically deployed change. Every report includes `can_auto_apply: false` and `agent_policies_modified: false`. An online rollout would additionally need stronger validation of task independence, evaluator integrity, policy compliance, safety constraints, potential multiple testing, and reproducibility on further workloads.

## Persistence, privacy, and existing behavior

The experiment schema is stored separately at `%LOCALAPPDATA%\Nykra\prospective.sqlite3` on Windows. This avoids migrating the live observer's `history.sqlite3` while it is running and preserves its older activity data. The trial's internal keyed-hashing secret stays in the local SQLite file, protected by the current OS user context; it is not a security boundary against programs running as that same user.

The Windows autostart observer continues passive Rel.AI and optional editor observation. No live Rel.AI host process, agent prompt, MCP tool schema, model weights, or IDE binary is modified in v0.7.

**Important distinction:** Synthetic tests validate Nykra's study mechanics. A real improvement claim requires a real authorized host to run genuinely assigned agent policies on newly encountered tasks with independently audited outcomes. Until such tasks have been collected, Nykra does not possess evidence of real agent improvement.
