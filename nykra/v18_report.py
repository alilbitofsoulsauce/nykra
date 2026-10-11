"""Audit task-level results of the pre-inference-frozen v0.18 real repair study."""
import hashlib
import json
from pathlib import Path

from .real_issue_v18 import ROOT, manifest

EVIDENCE = ROOT / "docs/evidence"

def summarize():
    protocol, expected_hash = manifest()
    rows=[]
    for task in protocol["tasks"]:
        filename = ("v18_pysnooper_3.json" if task["project"]=="PySnooper"
                    else f"v18_youtube_dl_{task['bug_id']}.json")
        path=EVIDENCE/filename
        if not path.exists():
            rows.append({"task":task["id"],"status":"not_run"})
            continue
        b=path.read_bytes()
        d=json.loads(b)
        if d["protocol_sha256"] != expected_hash or d["task_id"] != task["id"]:
            raise ValueError("mismatched immutable protocol or task ID")
        row={"task":task["id"],"project":task["project"],"status":d["status"],
             "raw_path":path.relative_to(ROOT).as_posix(),
             "raw_sha256":hashlib.sha256(b).hexdigest(),
             "eligible":bool((d.get("prevalidation") or {}).get("eligible"))}
        if d["status"]=="completed":
            a={x["arm"]:x for x in d["arms"]}
            if len(d["arms"])!=2 or set(a)!={"baseline","nykra"}:
                raise ValueError("incomplete paired arms")
            row["arms"]={}
            for arm in ("baseline","nykra"):
                x=a[arm]
                row["arms"][arm]={"public":x["public_pass"],
                    "hidden":x["hidden_pass"],"full":x["full_success"],
                    "attempts":x["attempts_used"],
                    "reported_tokens":x["reported_tokens"],
                    "token_reporting_complete":x["token_reporting_complete"],
                    "model_seconds":x["model_seconds"],
                    "model_calls_ok":sum(z["model_status"]=="ok" for z in x["attempts"]),
                    "branch_sequence":[{"kind":z["kind"],
                                        "parent_id":z["parent_attempt_id"]}
                                        for z in x["attempts"]]}
            left=row["arms"]["baseline"]["branch_sequence"]
            right=row["arms"]["nykra"]["branch_sequence"]
            row["policy_decisions_diverged"]=any(
                left[i]!=right[i] for i in range(min(len(left),len(right))))
        rows.append(row)
    finished=[x for x in rows if x["status"]=="completed"]
    excluded=[x for x in rows if x["status"]=="prevalidation_excluded"]
    wins={arm:sum(t["arms"][arm]["full"] for t in finished) for arm in ("baseline","nykra")}
    guided_only=sum(t["arms"]["nykra"]["full"] and not t["arms"]["baseline"]["full"] for t in finished)
    base_only=sum(t["arms"]["baseline"]["full"] and not t["arms"]["nykra"]["full"] for t in finished)
    # With one win in each direction the two-sided exact paired sign p-value
    # is 1.0. Store null if no discordant task pairs.
    n=guided_only+base_only
    if n:
        from math import comb
        left_tail=sum(comb(n,k) for k in range(min(guided_only,base_only)+1))/2**n
        two_sided_p=min(1.,2*left_tail)
    else:
        two_sided_p=None
    return {
        "schema":"nykra-real-issue-independent-v18-summary-v1",
        "protocol_sha256":expected_hash,
        "model":protocol["model"],
        "registered":len(rows),
        "paired_completed":len(finished),
        "prevalidation_excluded":len(excluded),
        "uncompleted":[x["task"] for x in rows if x["status"] not in
                       ("completed","prevalidation_excluded")],
        "successes":wins,
        "nykra_only":guided_only,
        "baseline_only":base_only,
        "two_sided_paired_sign_p":two_sided_p,
        "policy_decision_divergences":sum(x["policy_decisions_diverged"] for x in finished),
        "model_attempts":{arm:sum(x["arms"][arm]["attempts"] for x in finished)
                          for arm in ("baseline","nykra")},
        "reported_tokens":{arm:sum(x["arms"][arm]["reported_tokens"] for x in finished)
                           for arm in ("baseline","nykra")},
        "separate_hidden_cases":True,
        "multiple_upstream_repositories":True,
        "official_bugsinpy_harness":False,
        "official_swebench":False,
        "causal_policy_uplift_proven":False,
        "general_coding_agent_improvement_proven":False,
        "limit":"This is n=4 and no policy path diverged. Stochastic model variability can explain discordant successes. Soft token ceilings cannot bound a single call. Historical benchmark leakage is unknown.",
        "tasks":rows,
    }


def save():
    result=summarize()
    if result["uncompleted"]:
        raise ValueError("incomplete task set")
    path=EVIDENCE/"v18_summary.json"
    if path.exists():
        raise ValueError("will not overwrite saved study result")
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return path
