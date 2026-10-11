"""Issue-level, non-pooled v0.19 controlled-fork evidence aggregation."""
from __future__ import annotations

import hashlib
import json
from math import comb
from pathlib import Path

from .real_issue_v18 import ROOT
from .v19_fork_trial import fork_actions, protocol
from .v19_stalled_replay import manifest as stalled_protocol

EVIDENCE = ROOT / "docs/evidence"


def _load(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _two_sided_sign(guided_only: int, baseline_only: int):
    n = guided_only + baseline_only
    if not n:
        return None
    m = min(guided_only, baseline_only)
    return min(1., 2 * sum(comb(n,k) for k in range(m+1)) / 2**n)


def _pair(item, *, natural):
    result = {x["arm"]: x for x in item["arms"]}
    if len(item["arms"]) != 2 or set(result) != {"nykra","baseline"}:
        raise ValueError("task must have exactly both arms")
    a=result["baseline"]
    b=result["nykra"]
    expected_digest=hashlib.sha256(json.dumps(
        item["shared_prefix"],sort_keys=True).encode()).hexdigest()
    for arm in (a,b):
        if arm["common_prefix_sha256"]!=expected_digest:
            raise ValueError("arms did not inherit identical frozen prefix")
    if a["first_action"] != {"kind":"revise","parent_attempt_id":"attempt-3"}:
        raise ValueError("baseline failed policy fork")
    if b["first_action"] != {"kind":"new_root","parent_attempt_id":None}:
        raise ValueError("adaptive failed policy fork")
    return {
        "baseline": _arm(a),
        "nykra": _arm(b),
        "identical_shared_prefix_sha256": expected_digest,
        "verified_policy_fork": True,
        "natural": natural,
    }


def _arm(x):
    return {"success":bool(x["full_success"]),
            "public_pass":x["public_pass"],
            "hidden_pass":x["hidden_pass"],
            "calls":x["continuation_calls"],
            "tokens":x["continuation_usage"]["reported_tokens"],
            "tokens_complete":x["continuation_usage"]["tokens_complete"],
            "model_seconds":x["continuation_usage"]["model_seconds"],
            "stop_reason":x["stop_reason"]}


def _stats(pairs):
    guided=sum(x["nykra"]["success"] for x in pairs)
    baseline=sum(x["baseline"]["success"] for x in pairs)
    guided_only=sum(x["nykra"]["success"] and not x["baseline"]["success"]
                    for x in pairs)
    baseline_only=sum(x["baseline"]["success"] and not x["nykra"]["success"]
                      for x in pairs)
    return {"forked_pairs":len(pairs),
            "nykra_full_successes":guided,"baseline_full_successes":baseline,
            "nykra_only":guided_only,"baseline_only":baseline_only,
            "paired_two_sided_exact_sign_p":_two_sided_sign(guided_only,baseline_only),
            "model_reported_tokens_incremental":{
                arm:sum(x[arm]["tokens"] for x in pairs)
                for arm in ("baseline","nykra")},}


def build_report():
    p, sha=protocol()
    stalled, stalled_sha=stalled_protocol()
    natural=[]
    natural_pairs=[]
    for taskid in p["task_ids"]:
        filename=("v19_pysnooper_3.json" if taskid=="PySnooper-3"
                  else f"v19_youtube_dl_{taskid.rsplit('-',1)[1]}.json")
        path=EVIDENCE/filename
        d,digest=_load(path)
        if d["task_id"] != taskid or d["protocol_sha256"] != sha:
            raise ValueError("natural provenance changed")
        row={"task_id":taskid,"raw_path":path.relative_to(ROOT).as_posix(),
             "raw_sha256":digest,"status":d["status"],
             "shared_prefix_attempts":len(d["shared_prefix"]),
             "shared_prefix_public_solved":d["shared_prefix_reason"]=="public_solved"}
        if d["status"] == "completed":
            row["fork"]=_pair(d,natural=True)
            natural_pairs.append(row["fork"])
        elif d["status"] != "not_forkable":
            raise ValueError("incomplete natural task")
        natural.append(row)
    prefix_audit,prefix_sha=_load(EVIDENCE/"v19_shared_prefix_hidden.json")
    if prefix_audit["protocol_sha256"] != sha:
        raise ValueError("prefix hidden audit mismatch")
    if sorted(t["task_id"] for t in prefix_audit["tasks"]) != sorted(
            t["task_id"] for t in natural if t["shared_prefix_public_solved"]):
        raise ValueError("missing post-hoc shared prefix checks")
    if not prefix_audit["observed_after_all_model_calls"]:
        raise ValueError("hidden prefix audit timing unverified")
    archived=[]
    archived_pairs=[]
    for row in stalled["selected"]:
        taskid=row["task_id"]
        filename=("v19_stalled_pysnooper3.json" if taskid=="PySnooper-3"
                  else f"v19_stalled_yt{taskid.rsplit('-',1)[1]}.json")
        path=EVIDENCE/filename
        d,digest=_load(path)
        if d["task_id"] != taskid or d["protocol_sha256"] != stalled_sha:
            raise ValueError("secondary provenance changed")
        if d["status"] != "completed" or len(d["revalidation"])!=3 or any(
                r["status"] != "test_failed" for r in d["revalidation"]):
            raise ValueError("unverified stalled replay")
        item={"task_id":taskid,"raw_path":path.relative_to(ROOT).as_posix(),
              "raw_sha256":digest,"status":d["status"],
              "prefix_source":"original v18 recorded first 3 model attempts",
              "fork":_pair(d,natural=False)}
        archived.append(item)
        archived_pairs.append(item["fork"])
    return {
        "schema":"nykra-controlled-prefix-fork-v19-summary-v1",
        "natural_protocol_sha256":sha,
        "stalled_protocol_sha256":stalled_sha,
        "natural": {
            "registered":len(natural),
            "shared_public_solves":sum(x["shared_prefix_public_solved"] for x in natural),
            "shared_hidden_verified_posthoc":sum(
                x["hidden"]["passed"] for x in prefix_audit["tasks"]),
            "stats":_stats(natural_pairs),
            "tasks":natural,
        },
        "conditional_stalled_history":{
            "registered":len(archived),
            "conditioning":"chosen based on already-observed v18 three-failure histories; not prospectively sampled from unknown tasks",
            "stats":_stats(archived_pairs),
            "tasks":archived,
        },
        "shared_prefix_hidden_audit_path":"docs/evidence/v19_shared_prefix_hidden.json",
        "shared_prefix_hidden_audit_sha256":prefix_sha,
        "pooled_effect_estimate_valid":False,
        "causal_effect_generalized":False,
        "official_swebench":False,
        "official_bugsinpy_harness":False,
        "limitations":("Natural cohort had one forkable issue; secondary cohort deliberately conditions on historical failed samples, "
                       "includes the same PySnooper bug as natural study, and uses task already seen in v18. "
                       "One or two model calls per continuation remain stochastic and lack hard per-call token caps. "
                       "The grader reuses real old issues, with possible training contamination, and Docker is not certified hostile-code isolation."),
    }


def save_report():
    p=EVIDENCE/"v19_summary.json"
    if p.exists():
        raise ValueError("will not overwrite audited results")
    p.write_text(json.dumps(build_report(),indent=2)+"\n",encoding="utf-8")
    return p
