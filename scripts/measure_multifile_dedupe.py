"""Reproduce actual pinned-Docker duplicate public-test work avoidance.

Synthetic deterministic Git fixture only. This does not call an LLM, does not
run historical external code and never changes a developer repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from nykra import multifile_workflow as mw


IMAGE_PATTERN = re.compile(r"sha256:[0-9a-f]{64}$")
SEQ = (
    ("depth", ("A", "A", "A"), False),
    ("depth", ("A", "A", "A"), True),
    ("adaptive", ("A", "A", "B", "C"), True),
    ("adaptive", ("A", "A", "B", "C"), False),
)


def _git(repo, *args):
    command = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, timeout=40, check=True,
    )
    return command.stdout.decode("utf-8", errors="replace").strip()


def measure(*, image, approve=False):
    if approve is not True:
        raise ValueError("explicit Docker benchmark approval required")
    if not isinstance(image, str) or not IMAGE_PATTERN.fullmatch(image):
        raise ValueError("required: exact pinned sha256 Docker image ID")

    with tempfile.TemporaryDirectory(prefix="nykra-dedupe-v29-") as temporary:
        root = Path(temporary)
        repo = root / "fixture"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.name", "Nykra synthetic benchmark")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "core.autocrlf", "false")
        for folder in ("engine", "tests"):
            (repo / folder).mkdir()
            (repo / folder / "__init__.py").write_text("", encoding="utf-8")
        (repo / "engine/calc.py").write_text(
            "def total(a, b):\n    return a - b\n", encoding="utf-8", newline="\n",
        )
        (repo / "engine/routes.py").write_text(
            "from engine.calc import total\n"
            "def invoice(a, b):\n    return str(total(a, b) - 1)\n",
            encoding="utf-8", newline="\n",
        )
        (repo / "tests/test_invoice.py").write_text(
            "import unittest\nfrom engine.calc import total\n"
            "from engine.routes import invoice\n"
            "class InvoiceTest(unittest.TestCase):\n"
            "    def test_math(self): self.assertEqual(total(7,5),12)\n"
            "    def test_route(self): self.assertEqual(invoice(7,5),'12')\n",
            encoding="utf-8", newline="\n",
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "Original failing two-module synthetic fixture")
        fixture_head = _git(repo, "rev-parse", "HEAD")

        variants = {
            "A": ("return a + b", "return str(total(a, b) - 2)"),
            "B": ("return a * b", "return str(total(a, b))"),
            "C": ("return a + b + 1", "return str(total(a, b))"),
        }
        patches = {}
        for label, (math, result) in variants.items():
            (repo / "engine/calc.py").write_text(
                "def total(a, b):\n    " + math + "\n",
                encoding="utf-8", newline="\n",
            )
            (repo / "engine/routes.py").write_text(
                "from engine.calc import total\n"
                "def invoice(a, b):\n    " + result + "\n",
                encoding="utf-8", newline="\n",
            )
            patches[label] = _git(
                repo, "diff", "--", "engine/calc.py", "engine/routes.py",
            ) + "\n"
            if patches[label].count("diff --git a/") != 2:
                raise ValueError("expected two exact changed modules")
            _git(repo, "checkout", "--", "engine/calc.py", "engine/routes.py")
        if _git(repo, "status", "--porcelain"):
            raise ValueError("fixture was not clean before evaluating")

        results = []
        for policy, sequence, enabled in SEQ:
            home = root / ("history-" + policy + ("-reuse" if enabled else "-plain"))
            started = mw.start(
                repository=repo, task="Repair two-module invoice arithmetic",
                allowed_paths=["engine/calc.py", "engine/routes.py"],
                policy=policy, budget=4, dedupe_public=enabled,
                test_target="tests.test_invoice", docker_image_id=image,
                timeout=120, approve=True, home=home,
            )
            session = started["session_id"]
            attempts = []
            start = time.monotonic()
            for name in sequence:
                request = mw.next_request(session, home=home)
                before = time.monotonic()
                observation = mw.submit(
                    session, patches[name], approve=True, home=home,
                )["evaluated"]
                if (observation["status"] != "test_failed" or
                        observation["tests_run"] != 2 or
                        observation["tests_passed"]):
                    raise ValueError("unexpected public verdict in fixture")
                attempts.append({
                    "patch": name,
                    "controller_action": request["action"]["kind"],
                    "attempt_id": observation["id"],
                    "status": observation["status"],
                    "tests_run_original": observation["tests_run"],
                    "tests_executed_now": observation["public_tests_executed_now"],
                    "reused": observation["public_test_reused"],
                    "reused_from": observation["reused_from_attempt_id"],
                    "test_exit_code": observation["test_exit_code"],
                    "submit_wall_seconds": round(time.monotonic()-before, 4),
                })
            counters = mw.summary(session, home=home)["public_work"]
            final = mw.finalize(session, approve=True, home=home)
            if final["public_tests_passed"]:
                raise ValueError("unexpected public-passing patch")
            results.append({
                "policy": policy, "dedupe_enabled": enabled,
                "submitted_patches": list(sequence),
                "total_submit_wall_seconds": round(time.monotonic()-start, 4),
                "public_work": counters, "attempts": attempts,
                "finalized_without_passing_patch": True,
            })

        if _git(repo, "status", "--porcelain"):
            raise ValueError("fixture was modified by the workflow")
        without = sum(
            r["public_work"]["public_evaluator_calls"]
            for r in results if not r["dedupe_enabled"]
        )
        with_reuse = sum(
            r["public_work"]["public_evaluator_calls"]
            for r in results if r["dedupe_enabled"]
        )
        if (without, with_reuse) != (7, 4):
            raise ValueError("unexpected duplicate evaluator accounting")
        for record in results:
            if (record["public_work"]["model_attempts_recorded"] !=
                    len(record["submitted_patches"])):
                raise ValueError("duplicate replay changed model attempt budget")
        return {
            "schema": "nykra-real-docker-duplicate-work-replay-v1",
            "kind": "controlled deterministic trace-pattern replay, not model inference",
            "trace_source": "v0.28 depth A,A,A and adaptive A,A,B,C",
            "test_kind": "synthetic two-module intentionally failing Git patches",
            "fixture_head": fixture_head,
            "fixture_clean_after": True,
            "docker_image_id": image, "test_target": "tests.test_invoice",
            "patch_sha256": {
                key: hashlib.sha256(value.encode()).hexdigest()
                for key, value in patches.items()
            },
            "evaluator_calls_without_cache": without,
            "evaluator_calls_with_cache": with_reuse,
            "avoided_docker_evaluations": without-with_reuse,
            "avoided_fraction": (without-with_reuse)/without,
            "task_success_without_cache": False,
            "task_success_with_cache": False,
            "same_model_attempt_budgets": True,
            "opt_in_only": True,
            "wall_time_confounded_by_cold_warm_startup": True,
            "flaky_or_environment_sensitive_tests_must_not_use_cache": True,
            "runs": results,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(argv)
    report = measure(image=args.image, approve=args.approve)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("refusing to overwrite an existing benchmark receipt")
    args.output.write_text(json.dumps(report, indent=2)+"\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({
        "no_cache": report["evaluator_calls_without_cache"],
        "with_cache": report["evaluator_calls_with_cache"],
        "avoided": report["avoided_docker_evaluations"],
        "fraction": report["avoided_fraction"],
        "evidence_file": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
