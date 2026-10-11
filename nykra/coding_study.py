"""Reproducible locally executed evidence for model-authored coding candidates.

This is an executable test harness, NOT a model runner. It does not mistake
synthetic negative controls, deterministic code or assisted demonstrations for
independent LLM calls. Task generators and reference implementations are public
in the repository; do not claim a blind contamination-resistant benchmark.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .coding_worker import validate_source
from .relai_coding import evaluate_source
from .study_tasks import TASKS, cases
from .store import NykraError

EVALUATOR_ID="nykra-study-coding-v1"


def evaluate_frozen_candidates(candidate_file: Path, *, approval: bool = False) -> dict:
    if approval is not True:
        raise NykraError("explicit approval required to run candidate programs")
    if not candidate_file.is_file() or candidate_file.stat().st_size > 50000:
        raise NykraError("candidate manifest missing or too large")
    raw=candidate_file.read_bytes()
    try:
        sources=json.loads(raw)
    except (ValueError,UnicodeError):
        raise NykraError("invalid JSON candidate manifest") from None
    if not isinstance(sources,dict) or set(sources)!=set(TASKS):
        raise NykraError("manifest must contain each predeclared coding task exactly once")
    rows=[]
    for task in TASKS:
        candidate=sources[task]
        try:
            validate_source(candidate)
        except (SyntaxError,ValueError):
            raise NykraError("candidate contains unsupported or invalid Python") from None
        training=evaluate_source(task,candidate,heldout=False)
        heldout=evaluate_source(task,candidate,heldout=True)
        rows.append({
            "task_id":task,
            "initial_source_sha256":hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            "training_score":training,
            "heldout_score":heldout,
            "heldout_cases":len(cases(task,heldout=True)),
            "heldout_passed":round(heldout*len(cases(task,heldout=True))),
            "first_attempt_passed":heldout==1.0,
        })
    solved=sum(row["first_attempt_passed"] for row in rows)
    tests=sum(row["heldout_cases"] for row in rows)
    passed=sum(row["heldout_passed"] for row in rows)
    return {
        "study_id":"chatgpt-relai-coding-first-attempt-v1",
        "evaluator":EVALUATOR_ID,
        "candidate_manifest_sha256":hashlib.sha256(raw).hexdigest(),
        "task_family_count":len(rows),
        "initial_candidates":len(rows),
        "agent_provenance":"ChatGPT model-authored candidates submitted via Rel.AI by a connected assistant; not a separate unattended inference API.",
        "heldout_test_cases":tests,
        "heldout_test_cases_passed":passed,
        "first_attempt_tasks_passed":solved,
        "first_attempt_success_rate":solved/len(rows),
        "guided_revision_attempts":0,
        "measurable_uplift_tasks":0,
        "measurable_uplift_percentage_points":0.0,
        "task_rows":rows,
        "study_limits":{
            "baseline":"one model-authored first candidate per task; no matched independent-agent control arm",
            "tasks":"eight algorithmic Python challenges with separate deterministic public training and heldout generators; NOT repository issue fixes",
            "external_blinding":"none; tasks and reference implementations are in this source repository and the author can inspect them",
            "budget":"one candidate per task was needed; no attempt-matched randomized comparison possible because every initial candidate passed",
            "inference":"no statistically valid estimate of Nykra vs. no Nykra causal benefit; ceiling effect",
            "real_model_gain_proven":False,
            "zero_general_benefit_proven":False,
            "recursive_self_improvement_proven":False,
        },
    }
