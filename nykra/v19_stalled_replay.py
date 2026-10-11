"""Secondary v0.19 controlled fork conditional on archived real stalled prefixes.

Strictly independent experiment from v0.19's naturally generated prefixes.
Historical data was selected after the earlier v0.18 study and after the
v0.19 natural study, so report as CONDITIONAL exploratory analysis only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .real_issue_v18 import ROOT, grade
from .v19_fork_trial import (
    _task, _source, continue_arm, fork_actions, freeze_sha, protocol as main_protocol,
)

PROTOCOL = ROOT / "docs/evidence/v19_stalled_protocol.json"
ROOT_EVIDENCE = ROOT / "docs/evidence"


def manifest():
    raw = PROTOCOL.read_bytes()
    doc = json.loads(raw)
    first, original_sha = main_protocol()
    if doc["id"] != "nykra-v19-stalled-existing-prefixes-v1":
        raise ValueError("unexpected secondary protocol")
    if doc["prior_v19_protocol_sha256"] != original_sha:
        raise ValueError("main fork protocol changed")
    if doc["cohort_size"] != len(doc["selected"]):
        raise ValueError("cohort count discrepancy")
    if len({x["task_id"] for x in doc["selected"]}) != len(doc["selected"]):
        raise ValueError("duplicate task selection")
    if any(x["task_id"] not in first["task_ids"] for x in doc["selected"]):
        raise ValueError("unregistered issue")
    return doc, hashlib.sha256(raw).hexdigest()


def recorded_prefix(task_id):
    p, _ = manifest()
    selected = next((x for x in p["selected"] if x["task_id"] == task_id), None)
    if selected is None:
        raise ValueError("task not conditionally preregistered")
    # Read only specific pinned external histories, never unexpected paths.
    v18_path = ROOT / selected["v18_result_path"]
    if v18_path.parent.resolve() != ROOT_EVIDENCE.resolve():
        raise ValueError("historical evidence outside approved folder")
    if freeze_sha(v18_path) != selected["v18_raw_sha256"]:
        raise ValueError("historical evidence altered")
    src = json.loads(v18_path.read_bytes())
    arm = next((x for x in src["arms"] if x["arm"] == selected["source_arm"]), None)
    if arm is None:
        raise ValueError("archived arm missing")
    prefix = arm["attempts"][:3]
    digest = hashlib.sha256(json.dumps(prefix, sort_keys=True).encode()).hexdigest()
    if digest != selected["prefix_sha256"]:
        raise ValueError("archived prefix modified")
    main, _ = main_protocol()
    fork_actions(prefix, main)  # Verify true fork, never accept mere label.
    return prefix, selected


def replay(task_id, outfile: Path, *, approve=False, proposer=None):
    if approve is not True:
        raise ValueError("explicit authorization required")
    d, sha = manifest()
    if outfile.exists():
        raise ValueError("will not overwrite experiment data")
    prefix, frozen = recorded_prefix(task_id)
    task = _task(task_id)
    out = {"task_id": task_id, "protocol_sha256": sha,
           "status": "revalidating_archived_prefix",
           "selection": frozen,
           "shared_prefix": prefix, "revalidation": [],
           "fork_actions": None, "arms": []}
    outfile.parent.mkdir(parents=True, exist_ok=True)
    def checkpoint():
        stage = outfile.with_suffix(".partial")
        stage.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        os.replace(stage, outfile)
    checkpoint()
    # The old original public feedback must reproduce exactly in the
    # current Docker environment before performing fresh model continuations.
    for a in prefix:
        if a["model_status"] != "ok" or not isinstance(a.get("source"), str):
            out["status"] = "revalidation_excluded"
            checkpoint()
            return out
        verdict = grade(task, mode="public", candidate=a["source"])
        out["revalidation"].append({
            "candidate_sha256": a["source_sha256"], "status": verdict["status"],
            "passed": verdict["passed"]})
        checkpoint()
        if verdict["status"] != "test_failed":
            out["status"] = "revalidation_excluded"
            checkpoint()
            return out
    main, _ = main_protocol()
    out["fork_actions"] = fork_actions(prefix, main)
    out["status"] = "forking"
    checkpoint()
    broken = _source(task)
    for arm in d["continuation_arm_order"][task_id]:
        def partial(items):
            out["pending_arm"] = {"arm": arm, "continuation": items}
            checkpoint()
        score = continue_arm(task, broken, prefix, main, arm,
                             proposer=proposer, checkpoint=partial)
        out["arms"].append(score)
        out.pop("pending_arm", None)
        checkpoint()
    out["status"] = "completed"
    checkpoint()
    return out
