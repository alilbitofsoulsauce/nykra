"""Nykra command line and dependency-free synthetic smoke test."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .replay import POLICIES, replay
from .intelligence import assess_policies
from .prospective import ProspectiveExperiment
from .relai_coding import available_tasks, evaluate_source, run_proposal_trial, EVALUATOR_ID
from .iterative import IterativeCoding
from .relai_agent import RelaiAgent
from .drivers import scan_drivers, get_driver
from .benchmarks import paired_reference_benchmark
from .coding_study import evaluate_frozen_candidates
from .external_isolation import isolation_preflight
from .container_smoke import run_container_smoke
from .relai_history import RelaiHistoryObserver, default_relai_database
from .install import install_user, installed_status, start_installed, uninstall_user
from .ide import detect_ides, package_vsix, manage_extension
from .workstation import read_health, request_stop, run_runtime
from .server import create_server
from .store import HistoryStore, NykraError


def _output(result: Any) -> None:
    print(json.dumps(result, indent=2, allow_nan=False))


def _demo() -> dict[str, Any]:
    # Purely synthetic fixtures: demonstration only, not evidence of improvement.
    with tempfile.TemporaryDirectory(prefix="nykra-demo-") as directory:
        store = HistoryStore(Path(directory))
        run = store.create_run(task="Synthetic optimization example", agent="fixture",
                               evaluator_id="fixture-v1", objective="maximize")
        run_id = run["id"]
        store.record_attempt(run_id=run_id, attempt_id="a", score=1.0, cost_units=1)
        store.record_attempt(run_id=run_id, attempt_id="b", score=2.0, cost_units=1)
        store.record_attempt(run_id=run_id, attempt_id="a1", parent_id="a", score=1.1)
        store.record_attempt(run_id=run_id, attempt_id="b1", parent_id="b", score=4.5)
        store.record_attempt(run_id=run_id, attempt_id="a2", parent_id="a1", status="failed",
                             metadata={"failure": "synthetic evaluator error"})
        return {
            "note": "Synthetic fixtures only; these numbers do not demonstrate real-world gains.",
            "comparison": {
                policy: replay(store, run_id=run_id, policy=policy, budget=4, workers=1)
                for policy in POLICIES
            },
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nykra", description="Agent-agnostic evidence collection and historical policy replay.")
    parser.add_argument("--home", type=Path, default=None,
                        help="optional local data directory; defaults to per-user application data")
    parser.add_argument("--version", action="version", version=f"nykra {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show local history database statistics")
    integrations = sub.add_parser("integrations", help="discover driver capabilities without auto-installing agents")
    integrations.add_argument("action", choices=["scan"])
    paired = sub.add_parser("benchmark", help="equal-budget paired reference search benchmark (not LLM evaluation)")
    paired.add_argument("action", choices=["paired-grid", "preflight", "smoke"])
    paired.add_argument("--tasks", type=int, default=48)
    paired.add_argument("--budget", type=int, default=12)
    paired.add_argument("--seed", type=int, default=20261011)
    paired.add_argument("--image", default=None, help="locally available digest-pinned container image for external benchmark checks")
    paired.add_argument("--approve", action="store_true", help="explicitly authorize reference worker subprocesses")
    activity = sub.add_parser("activity", help="show minimal tool observations from connected runtimes")
    activity.add_argument("--source", default=None)
    activity.add_argument("--limit", type=int, default=20)
    sub.add_parser("demo", help="run a synthetic replay example without touching your database")
    study = sub.add_parser("coding-study", help="evaluate frozen model-authored coding candidates on separate held-out cases")
    study.add_argument("--candidates-file", type=Path, required=True)
    study.add_argument("--approve", action="store_true")
    ide = sub.add_parser("ide", help="discover, package or manage supported VS Code-family IDE adapters")
    ide.add_argument("action", choices=["scan", "package", "install", "uninstall"])
    ide.add_argument("--target", choices=["all", "vscode", "cursor", "windsurf", "vscodium"], default="all")
    ide.add_argument("--dry-run", action="store_true")
    sub.add_parser("install", help="install Nykra for this Windows user and start background observation")
    sub.add_parser("uninstall", help="stop and remove managed autostart; preserve historical data")
    sub.add_parser("doctor", help="show installed runtime, Rel.AI detection and local health")
    background = sub.add_parser("background", help="manage installed Nykra background observer")
    background.add_argument("action", choices=["start", "stop", "status"])
    daemon = sub.add_parser("daemon", help="internal, foreground observer runtime")
    daemon.add_argument("--interval", type=float, default=2.0)
    daemon.add_argument("--source-db", type=Path, default=None)
    watcher = sub.add_parser("watch-relai", help="observe compatible Rel.AI history without modifying the host")
    watcher.add_argument("--source-db", type=Path, default=None)
    watcher.add_argument("--interval", type=float, default=2.0)
    watcher.add_argument("--once", action="store_true", help="perform one pass and exit")
    watcher.add_argument("--backfill", action="store_true", help="explicitly import the most recent history page")
    serve = sub.add_parser("serve", help="run local authenticated ingestion server")
    serve.add_argument("--port", type=int, default=8765)

    start = sub.add_parser("start", help="record a new evaluated exploration run")
    start.add_argument("--task", required=True)
    start.add_argument("--agent", required=True)
    start.add_argument("--evaluator", required=True)
    start.add_argument("--objective", choices=["maximize", "minimize"], default="maximize")

    attempt = sub.add_parser("attempt", help="record one evaluated candidate")
    attempt.add_argument("--run", required=True)
    attempt.add_argument("--parent")
    attempt.add_argument("--id", dest="attempt_id")
    attempt.add_argument("--status", choices=["ok", "failed", "invalid"], default="ok")
    attempt.add_argument("--score", type=float)
    attempt.add_argument("--cost", type=float, default=1.0)
    attempt.add_argument("--elapsed-ms", type=float, default=0.0)
    attempt.add_argument("--snapshot")

    assessment = sub.add_parser("assess", help="task-disjoint retrospective policy comparison (advisory only)")
    assessment.add_argument("--evaluator", required=True, help="trusted evaluator version, not a tool/agent name")
    assessment.add_argument("--objective", choices=["maximize", "minimize"], default="maximize")
    assessment.add_argument("--budget", type=int, default=2)
    assessment.add_argument("--min-train", type=int, default=8)
    assessment.add_argument("--min-heldout", type=int, default=8)
    sub.add_parser("intelligence-demo", help="synthetic training/holdout assessment, no live agent execution")
    sub.add_parser("prospective-demo", help="synthetic randomized policy experiment, no real agent calls")
    coding = sub.add_parser("coding", help="Rel.AI-mediated supervised coding-task experiment")
    coding.add_argument("action", choices=["tasks","evaluate","trial"])
    coding.add_argument("--task", default=None)
    coding.add_argument("--candidate-file", type=Path, default=None)
    coding.add_argument("--pool-file", type=Path, default=None)
    coding.add_argument("--trial", default=None)
    coding.add_argument("--task-key", default=None)
    coding.add_argument("--approve", action="store_true")
    relai = sub.add_parser("relai-agent", help="Rel.AI-first one-request-at-a-time coding-agent loop")
    relai.add_argument("action", choices=["start", "next", "submit", "finalize", "abort"])
    relai.add_argument("--session", default=None)
    relai.add_argument("--task", choices=list(available_tasks()), default=None)
    relai.add_argument("--policy", choices=["breadth", "depth", "adaptive"], default="depth")
    relai.add_argument("--budget", type=int, default=4)
    relai.add_argument("--threshold", type=float, default=1.0)
    relai.add_argument("--max-seconds", type=float, default=1200)
    relai.add_argument("--trial", default=None)
    relai.add_argument("--task-key", default=None)
    relai.add_argument("--candidate-file", type=Path, default=None)
    relai.add_argument("--approve", action="store_true")
    loop = sub.add_parser("iterate", help="durable, feedback-driven external-agent coding sessions")
    loop.add_argument("action", choices=["start","next","submit","finish","abort"])
    loop.add_argument("--session", default=None)
    loop.add_argument("--task", choices=list(available_tasks()), default=None)
    loop.add_argument("--policy", choices=["breadth","depth","adaptive"], default="depth")
    loop.add_argument("--budget", type=int, default=4)
    loop.add_argument("--threshold", type=float, default=1.0)
    loop.add_argument("--max-seconds", type=float, default=600)
    loop.add_argument("--trial", default=None)
    loop.add_argument("--task-key", default=None)
    loop.add_argument("--candidate-file", type=Path, default=None)
    loop.add_argument("--approve", action="store_true")
    benchmark = sub.add_parser("agent-benchmark", help="run an explicitly approved subprocess search-agent benchmark")
    benchmark.add_argument("--approve", action="store_true", help="allow temporary trusted worker subprocesses")
    benchmark.add_argument("--tasks", type=int, default=40)
    benchmark.add_argument("--budget", type=int, default=12)
    benchmark.add_argument("--seed", type=int, default=73)
    prospective = sub.add_parser("prospective", help="manage opt-in prospective trial protocol")
    prospective.add_argument("action", choices=["create", "assign", "claim", "finish", "report", "close"])
    prospective.add_argument("--trial", default=None)
    prospective.add_argument("--task-key", default=None)
    prospective.add_argument("--assignment", default=None)
    prospective.add_argument("--status", choices=["completed","failed","budget_violation","timeout_violation"], default=None)
    prospective.add_argument("--score", type=float, default=None)
    prospective.add_argument("--attempts-used", type=int, default=None)
    prospective.add_argument("--cost", type=float, default=None)
    prospective.add_argument("--elapsed-ms", type=float, default=None)
    prospective.add_argument("--evaluator", default=None)
    prospective.add_argument("--challenger", choices=["depth", "adaptive"], default="depth")
    prospective.add_argument("--objective", choices=["maximize", "minimize"], default="maximize")
    prospective.add_argument("--threshold", type=float, default=None)
    prospective.add_argument("--attempt-budget", type=int, default=6)
    prospective.add_argument("--seconds-budget", type=float, default=180)
    prospective.add_argument("--max-tasks", type=int, default=200)
    prospective.add_argument("--min-per-arm", type=int, default=20)
    prospective.add_argument("--min-effect", type=float, default=0.05)
    prospective.add_argument("--approve", action="store_true",
                             help="explicitly permit creating a prospective experiment")

    transaction = sub.add_parser("patch-transaction", help="Test multi-file Git patches in a disposable checkout; optionally promote atomically with rollback")
    transaction.add_argument("--repository", type=Path, required=True)
    transaction.add_argument("--patch-file", type=Path, required=True)
    transaction.add_argument("--allow", dest="allowed_paths", action="append", required=True,
                             help="Exact relative file path authorized for patching; repeat per path")
    transaction.add_argument("--test-target", default=None,
                             help="Dotted Python unittest module; defaults to unittest discover -s tests")
    transaction.add_argument("--docker-image-id", default=None,
                             help="Immutable sha256:... image ID; required for Docker executor")
    transaction.add_argument("--trusted-local-tests", action="store_true",
                             help="Explicitly allow running trusted repository tests directly on the workstation")
    transaction.add_argument("--promote", action="store_true",
                             help="After passing tests, atomically replace exact tested file bytes in the clean original worktree")
    transaction.add_argument("--approve", action="store_true")
    transaction.add_argument("--timeout", type=int, default=90)
    provider = sub.add_parser("provider-probe", help="Approval-gated external agent CLI readiness; no paid model invocation by Nykra")
    provider.add_argument("--expect", default="READY")
    provider.add_argument("--timeout", type=int, default=30)
    provider.add_argument("--runs", type=int, default=1)
    provider.add_argument("--approve", action="store_true")
    provider.add_argument("--cwd", type=Path, default=None)
    provider.add_argument("argv", nargs=argparse.REMAINDER,
                          help="Executable and arguments after --; no shell or API key handling")
    multi = sub.add_parser("multi-workflow", help="Portable approved multi-file agent proposals using disposable Git tests")
    multi.add_argument("action", choices=["start", "next", "submit", "finalize", "summary", "abort"])
    multi.add_argument("--repository", type=Path, default=None)
    multi.add_argument("--task", default=None)
    multi.add_argument("--allow", action="append", dest="allowed_paths", default=None)
    multi.add_argument("--policy", choices=["breadth", "depth", "adaptive"], default="depth")
    multi.add_argument("--budget", type=int, default=4)
    multi.add_argument("--session", default=None)
    multi.add_argument("--candidate-file", type=Path, default=None)
    multi.add_argument("--test-target", default=None)
    multi.add_argument("--docker-image-id", default=None)
    multi.add_argument("--trusted-local-tests", action="store_true")
    multi.add_argument("--dedupe-public", action="store_true",
                       help="Opt in to same-session exact failed-patch public receipt reuse")
    multi.add_argument("--halt-on-repeat-failure", action="store_true",
                       help="Opt in to pause new model requests after identical consecutive failed patches")
    multi.add_argument("--timeout", type=int, default=90)
    multi.add_argument("--approve", action="store_true")
    workflow = sub.add_parser("workflow", help="Rel.AI-hosted real Git repair sessions with portable proposal protocol")
    workflow.add_argument("action", choices=["tasks", "start", "next", "submit", "reuse", "finalize", "summary", "abort", "auto"])
    workflow.add_argument("--task", default=None)
    workflow.add_argument("--policy", choices=["breadth", "depth", "adaptive"], default="depth")
    workflow.add_argument("--budget", type=int, default=4)
    workflow.add_argument("--driver", choices=["relai-supervised", "codex-inference"], default="relai-supervised")
    workflow.add_argument("--session", default=None)
    workflow.add_argument("--verified-session", default=None,
                          help="Reuse an already executed identical public patch/test receipt")
    workflow.add_argument("--candidate-file", type=Path, default=None)
    workflow.add_argument("--status-only", action="store_true")
    workflow.add_argument("--cache-public", action="store_true",
                          help="Opt in to exact-source host-local persistent public Git/Docker receipt cache on submit")
    workflow.add_argument("--approve", action="store_true")
    sim = sub.add_parser("replay", help="compare exploration decisions on recorded outcomes")
    sim.add_argument("--run", required=True)
    sim.add_argument("--policy", choices=[*POLICIES, "all"], default="all")
    sim.add_argument("--budget", type=int, default=None)
    sim.add_argument("--workers", type=int, default=1)
    sim.add_argument("--cost-weight", type=float, default=0.0)
    sim.add_argument("--parallelism-weight", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            _output(_demo())
            return 0
        if args.command == "intelligence-demo":
            from .intelligence_demo import synthetic_demo
            _output(synthetic_demo())
            return 0
        if args.command == "coding-study":
            _output(evaluate_frozen_candidates(args.candidates_file, approval=args.approve))
            return 0
        if args.command == "benchmark":
            if args.action == "preflight":
                _output(isolation_preflight(image=args.image))
            elif args.action == "smoke":
                _output(run_container_smoke(image=args.image, approval=args.approve))
            else:
                _output(paired_reference_benchmark(count=args.tasks, budget=args.budget,
                                                   seed=args.seed, approval=args.approve))
            return 0
        if args.command == "integrations":
            _output(scan_drivers())
            return 0
        if args.command == "provider-probe":
            from .provider_preflight import probe_repeated
            argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
            _output(probe_repeated(argv, runs=args.runs, expect=args.expect,
                                   timeout=args.timeout, approve=args.approve,
                                   cwd=args.cwd))
            return 0
        if args.command == "patch-transaction":
            from .transactional_patch import run_transaction, PatchRejected
            import re
            if args.patch_file.stat().st_size > 128 * 1024:
                raise NykraError("patch exceeds 128 KiB limit")
            test_args = ("-B", "-m", "unittest", "discover", "-s", "tests")
            if args.test_target is not None:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,120}", args.test_target):
                    raise NykraError("invalid unittest target")
                test_args = ("-B", "-m", "unittest", args.test_target)
            _output(run_transaction(root=args.repository,
                                    patch=args.patch_file.read_text(encoding="utf-8"),
                                    allowed_paths=args.allowed_paths,
                                    test_args=test_args,
                                    executor=("local" if args.trusted_local_tests else "docker"),
                                    docker_image_id=args.docker_image_id,
                                    allow_trusted_local_tests=args.trusted_local_tests,
                                    promote=args.promote, approve=args.approve,
                                    timeout=args.timeout))
            return 0
        if args.command == "multi-workflow":
            from . import multifile_workflow as mw
            if args.action == "start":
                if args.repository is None or args.task is None or not args.allowed_paths:
                    raise NykraError("multi-workflow start requires --repository, --task and --allow")
                _output(mw.start(repository=args.repository, task=args.task,
                                 allowed_paths=args.allowed_paths, policy=args.policy,
                                 budget=args.budget, docker_image_id=args.docker_image_id,
                                 trusted_local_tests=args.trusted_local_tests,
                                 test_target=args.test_target, timeout=args.timeout,
                                 dedupe_public=args.dedupe_public,
                                 halt_on_repeat_failure=args.halt_on_repeat_failure,
                                 approve=args.approve, home=args.home))
            else:
                if args.session is None:
                    raise NykraError("multi-workflow action requires --session")
                if args.action == "next":
                    _output(mw.next_request(args.session, home=args.home))
                elif args.action == "submit":
                    if args.candidate_file is None:
                        raise NykraError("multi-workflow submit requires --candidate-file")
                    if args.candidate_file.stat().st_size > 128 * 1024:
                        raise NykraError("candidate patch exceeds 128 KiB")
                    _output(mw.submit(args.session, args.candidate_file.read_text(encoding="utf-8"),
                                      approve=args.approve, home=args.home))
                elif args.action == "finalize":
                    _output(mw.finalize(args.session, approve=args.approve, home=args.home))
                elif args.action == "abort":
                    _output(mw.abort(args.session, approve=args.approve, home=args.home))
                else:
                    _output(mw.summary(args.session, home=args.home))
            return 0
        if args.command == "workflow":
            from . import agent_workflow as wf
            if args.action == "tasks":
                from .v21_trial import validated_protocol
                document, protocol_sha, preflight = validated_protocol()
                _output({"evaluator_sha256": protocol_sha,
                         "tasks": [{"id": x["id"], "eligible": next(y["eligible"] for y in preflight["tasks"] if y["id"] == x["id"])} for x in document["tasks"]],
                         "driver_protocol": "portable-workflow-v1", "host": "relai-supervised"})
            elif args.action in ("start", "auto"):
                if args.task is None or not args.approve:
                    raise NykraError("workflow start/auto requires --task and --approve")
                if args.action == "auto":
                    _output(wf.run_with_provider(task_id=args.task, policy=args.policy,
                             budget=args.budget, driver="codex-inference",
                             enriched_feedback=not args.status_only))
                else:
                    _output(wf.start(task_id=args.task, policy=args.policy,
                             budget=args.budget, driver=args.driver,
                             enriched_feedback=not args.status_only, approve=True))
            else:
                if args.session is None:
                    raise NykraError("workflow action requires --session")
                if args.action == "next":
                    _output(wf.next_request(args.session))
                elif args.action == "submit":
                    if args.candidate_file is None or not args.approve:
                        raise NykraError("workflow submit requires --candidate-file and --approve")
                    if args.candidate_file.stat().st_size > wf.SOURCE_BYTES:
                        raise NykraError("workflow candidate file exceeds 10KB")
                    _output(wf.submit(args.session, args.candidate_file.read_text(encoding="utf-8"),
                                      approve=True, agent_label=args.driver,
                                      cache_public=args.cache_public))
                elif args.action == "reuse":
                    if not args.verified_session or not args.approve:
                        raise NykraError("workflow reuse requires --verified-session and --approve")
                    _output(wf.share_attempt(args.session, args.verified_session, approve=True))
                elif args.action == "finalize":
                    _output(wf.finalize(args.session, approve=args.approve))
                elif args.action == "abort":
                    _output(wf.abort(args.session, approve=args.approve))
                else:
                    _output(wf.summary(args.session))
            return 0
        if args.command == "prospective-demo":
            from .prospective_demo import demo
            _output(demo())
            return 0
        if args.command == "agent-benchmark":
            from .agent_host import run_reference_benchmark
            _output(run_reference_benchmark(count=args.tasks, budget=args.budget,
                                            seed=args.seed, approval=args.approve))
            return 0
        store = HistoryStore(args.home)
        if args.command == "status":
            _output(store.stats())
        elif args.command == "activity":
            _output(store.list_activity(source=args.source, limit=args.limit))
        elif args.command == "install":
            _output(install_user(args.home, activate=True))
        elif args.command == "uninstall":
            _output(uninstall_user(args.home))
        elif args.command == "background":
            if args.action == "start":
                _output(start_installed(args.home))
            elif args.action == "stop":
                _output(request_stop(args.home))
            else:
                _output(read_health(args.home))
        elif args.command == "daemon":
            _output(run_runtime(args.home, interval=args.interval, source_db=args.source_db))
        elif args.command == "ide":
            if args.action == "scan":
                _output({"detected": detect_ides()})
            elif args.action == "package":
                _output({"vsix": str(package_vsix())})
            else:
                _output(manage_extension(args.action, target=args.target, dry_run=args.dry_run))
        elif args.command == "doctor":
            _output({
                "version": __version__,
                "installed": installed_status(args.home),
                "relai_database_detected": default_relai_database().is_file(),
                "history": store.stats(),
                "replay_available": True,
                "agentic_ide_auto_integration": False,
                "compatible_ide_clis": [entry["id"] for entry in detect_ides() if entry["cli_detected"]],
                "ide_events_recorded": store.stats()["ide_activity_count"],
            })
        elif args.command == "watch-relai":
            observer = RelaiHistoryObserver(store, args.source_db)
            if args.once:
                _output(observer.poll(backfill=args.backfill))
            else:
                if args.backfill:
                    observer.poll(backfill=True)
                print("Observing Rel.AI history in read-only mode (Ctrl+C to stop)", flush=True)
                observer.watch(poll_seconds=args.interval, resume=args.backfill)
                _output(observer.report())
        elif args.command == "serve":
            store.token()
            server = create_server(store, args.port)
            print(f"Nykra listening on http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        elif args.command == "start":
            _output(store.create_run(task=args.task, agent=args.agent, evaluator_id=args.evaluator,
                                     objective=args.objective))
        elif args.command == "attempt":
            _output(store.record_attempt(run_id=args.run, parent_id=args.parent,
                                         status=args.status, score=args.score,
                                         cost_units=args.cost, elapsed_ms=args.elapsed_ms,
                                         snapshot_ref=args.snapshot, attempt_id=args.attempt_id))
        elif args.command == "relai-agent":
            agent = get_driver("relai", store)
            if args.action == "start":
                if args.task is None or not args.approve:
                    raise NykraError("Rel.AI agent start requires --task and --approve")
                _output(agent.start(task_id=args.task, policy=args.policy, budget=args.budget,
                                    max_seconds=args.max_seconds, threshold=args.threshold,
                                    trial_id=args.trial, task_key=args.task_key, approval=True))
            else:
                if args.session is None:
                    raise NykraError("Rel.AI agent action requires --session")
                if args.action == "next":
                    _output(agent.next(args.session))
                elif args.action == "submit":
                    if args.candidate_file is None or not args.approve:
                        raise NykraError("submit requires --candidate-file and --approve")
                    if args.candidate_file.stat().st_size > 5000:
                        raise NykraError("candidate file exceeds maximum size")
                    source = args.candidate_file.read_text(encoding="utf-8")
                    _output(agent.submit(args.session, source=source, approval=True))
                elif args.action == "finalize":
                    _output(agent.finalize(args.session, approval=args.approve))
                else:
                    _output(agent.abort(args.session, approval=args.approve))
        elif args.command == "iterate":
            loop = IterativeCoding(store)
            if args.action == "start":
                if args.task is None or not args.approve:
                    raise NykraError("start requires --task and --approve")
                _output(loop.start(task_id=args.task, policy=args.policy,
                                   budget=args.budget, threshold=args.threshold,
                                   max_seconds=args.max_seconds, trial_id=args.trial,
                                   task_key=args.task_key, approval=True))
            else:
                if args.session is None:
                    raise NykraError("iterate action requires --session")
                if args.action == "next":
                    _output(loop.status(args.session))
                elif args.action in ("submit", "finish"):
                    if not args.approve or args.candidate_file is None:
                        raise NykraError("submit/finish requires --candidate-file and --approve")
                    if args.candidate_file.stat().st_size > 5000:
                        raise NykraError("candidate source file exceeds limit")
                    source = args.candidate_file.read_text(encoding="utf-8")
                    if args.action == "submit":
                        _output(loop.submit(args.session, source=source, approval=True))
                    else:
                        _output(loop.finish(args.session, best_source=source, approval=True))
                else:
                    _output(loop.abort(args.session, approval=args.approve))
        elif args.command == "coding":
            if args.action == "tasks":
                _output({"tasks": available_tasks(), "evaluator_id": EVALUATOR_ID,
                         "mode": "explicit_supervisor_model_proposals_via_relai"})
            elif args.action == "evaluate":
                if not args.approve or args.task is None or args.candidate_file is None:
                    raise NykraError("evaluate requires --approve, --task and --candidate-file")
                source = args.candidate_file.read_text(encoding="utf-8")
                _output({"task_id": args.task,
                         "training_score": evaluate_source(args.task, source, heldout=False),
                         "heldout_score": evaluate_source(args.task, source, heldout=True),
                         "source_persisted": False})
            else:
                if not args.approve or args.pool_file is None or args.trial is None or args.task_key is None:
                    raise NykraError("trial requires --approve, --pool-file, --trial and --task-key")
                if args.pool_file.stat().st_size > 100000:
                    raise NykraError("coding pool file too large")
                pool = json.loads(args.pool_file.read_text(encoding="utf-8"))
                _output(run_proposal_trial(store, trial_id=args.trial, task_key=args.task_key,
                                           pool=pool, approval=True))
        elif args.command == "prospective":
            trial = ProspectiveExperiment(store)
            if args.action == "create":
                if args.evaluator is None or args.threshold is None:
                    raise NykraError("create requires --evaluator and --threshold")
                _output(trial.create(evaluator_id=args.evaluator, objective=args.objective,
                                     threshold=args.threshold, challenger=args.challenger,
                                     approval=args.approve, attempt_budget=args.attempt_budget,
                                     seconds_budget=args.seconds_budget, max_tasks=args.max_tasks,
                                     min_per_arm=args.min_per_arm, min_effect=args.min_effect))
            elif args.action == "assign":
                if args.trial is None or args.task_key is None:
                    raise NykraError("assign requires --trial and --task-key")
                _output(trial.assign(trial_id=args.trial, task_key=args.task_key))
            elif args.action == "claim":
                if args.trial is None or args.assignment is None:
                    raise NykraError("claim requires --trial and --assignment")
                _output(trial.claim(trial_id=args.trial, assignment_id=args.assignment))
            elif args.action == "finish":
                if args.trial is None or args.assignment is None or args.status is None:
                    raise NykraError("finish requires --trial, --assignment and --status")
                _output(trial.finish(trial_id=args.trial, assignment_id=args.assignment,
                                     status=args.status, score=args.score,
                                     attempts_used=args.attempts_used, cost_units=args.cost,
                                     elapsed_ms=args.elapsed_ms))
            elif args.action == "report":
                if args.trial is None:
                    raise NykraError("report requires --trial")
                _output(trial.report(args.trial))
            else:
                if args.trial is None:
                    raise NykraError("close requires --trial")
                _output(trial.close(args.trial))
        elif args.command == "assess":
            _output(assess_policies(store, evaluator_id=args.evaluator, objective=args.objective,
                                    budget=args.budget, min_train_tasks=args.min_train,
                                    min_heldout_tasks=args.min_heldout))
        elif args.command == "replay":
            policies = POLICIES if args.policy == "all" else (args.policy,)
            reports = [replay(store, run_id=args.run, policy=p, budget=args.budget,
                              workers=args.workers, cost_weight=args.cost_weight,
                              parallelism_weight=args.parallelism_weight) for p in policies]
            _output(reports if args.policy == "all" else reports[0])
        return 0
    except (NykraError, OSError, ValueError) as exc:
        print(f"nykra: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
