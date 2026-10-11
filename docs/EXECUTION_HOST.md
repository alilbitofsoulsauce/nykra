# Nykra v0.8 — Executable exploration host

**Scope:** v0.8 demonstrates that policy assignment changes which previously unseen candidate states a *separate, executable search-agent process* explores. It uses a small deterministic maze-search agent, not an LLM or a coding agent. It does **not** currently steer the installed Rel.AI host, Cursor, Windsurf or another model's internal thinking. This is a practical, testable execution boundary for future supported agent integrations.

## Demonstrate live candidate generation

From the Nykra checkout:

```powershell
python -m nykra agent-benchmark --tasks 40 --budget 12 --approve
```

Nykra generates 40 fresh bounded grid tasks in a temporary directory. Each is randomly allocated under the existing prospective trial protocol to **breadth** (baseline) or **adaptive** (challenger) before execution begins. For each task, the separate worker process proposes *new* immediate moves at run time; Nykra's host maintains and selects the frontier according to the assigned policy. The host counts actual expansions, enforces a budget and a time limit, and passes the chosen candidate path to an independent path validator. Failures, timeouts and budget violations count against the assigned arm, rather than being dropped.

The benchmark reports intent-to-treat success rates, arm sizes, test statistics (if the sample gate is met), and anonymous digests of a few actual visited-state traces. The worker and evaluator are distinct code paths. Only the final metrics are written to a disposable prospective database, which disappears after the demonstration.

**Interpretation:** This demonstrates *actual controlled search* and evaluator feedback, not an LLM improvement. The maze agent has no model weights, tools, cloud connection or ability to read external repositories. Any reported advantage is a result on these reference maze tasks only, with no claim about complex software engineering or general agent performance. An "advisory_candidate" output never auto-deploys.

## Subprocess worker protocol

A supervisor can create `SubprocessSearchHost(worker_argv=...)` with explicit arguments for a **trusted** external agent process. Nykra invokes the worker with `shell=False` and passes one UTF-8 JSON request on stdin:

```json
{
  "task": {"width": 4, "height": 4, "walls": [], "start": [0, 0], "goal": [3, 3]},
  "path": [[0, 0]]
}
```

The worker must return exactly one JSON object on stdout containing at most four children:

```json
{
  "children": [
    {"path": [[0, 0], [0, 1]], "heuristic": 5},
    {"path": [[0, 0], [1, 0]], "heuristic": 5}
  ]
}
```

The host rejects illegal steps, duplicate positions, invalid schemas, blocked cells, giant responses, and non-finite heuristic values. Worker-supplied heuristics are **not** evaluator scores. Only *previously revealed* state and legal frontier metadata affect the host's decision. The independent evaluator checks the complete path, boundaries, wall collisions and goal attainment; it does not trust worker self-ratings.

The included `nykra/reference_agent.py` is a simple, deterministic, dependency-free worker. It actually computes candidate next steps at runtime. You can replace it with an authorized model agent implementing the protocol, but that must be separately connected, verified and evaluated. Subprocess execution is **not an OS security sandbox**, and running an untrusted worker could still be dangerous even with reduced environment variables and temporary working directories. Never point this API at an unknown binary.

## Host wiring

```python
from nykra.agent_host import SubprocessSearchHost, evaluate_grid
from nykra.prospective import ProspectiveExperiment
from nykra.store import HistoryStore

store = HistoryStore()
trial_engine = ProspectiveExperiment(store)
trial = trial_engine.create(
    evaluator_id="grid-verifier-v1", objective="maximize",
    threshold=1.0, challenger="adaptive", approval=True,
    attempt_budget=12, seconds_budget=20, max_tasks=80,
)

host = SubprocessSearchHost()  # packaged reference worker, not an LLM
task = {
    "width": 4, "height": 4, "walls": [[1,1]],
    "start": [0,0], "goal": [3,3]
}
result = trial_engine.run_task(
    trial_id=trial["id"], task_key="new-grid-task-001",
    task=task, execute=host.execute, evaluate=evaluate_grid,
    approval=True,
)
```

The host is responsible for selecting which authorized worker to use, gaining permission, isolating task side effects, and independently verifying task outcomes. A genuine coding-agent adapter will need a distinct task/environment schema, fixture generation, snapshot management, safe tool APIs and reproducible software tests. Nykra currently **does not** provide those capabilities for the installed Rel.AI agent.

## Health and existing installation

Nykra's Windows background observer remains a separate, passive component. It keeps collecting authorized Rel.AI tool-completion metadata into `history.sqlite3` and does not run experimental agent subprocesses in the background. The benchmark requires an explicit `--approve` flag, runs in a temporary directory, and does not modify live Rel.AI or any Git repository.

For the existing v0.7 prospective database schema and trial reporting behavior, see [PROSPECTIVE.md](PROSPECTIVE.md). Nykra still refuses to silently apply experimental policy recommendations.
