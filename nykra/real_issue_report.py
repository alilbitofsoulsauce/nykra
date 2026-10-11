"""Summarize actual historical-issue repair outcomes without inflating claims."""
import hashlib
import json
import math
from pathlib import Path

from .real_issue_trial import PROTOCOL, read_manifest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"


def summarize(require_complete=False):
    manifest, expected = read_manifest()
    items = []
    for task in manifest["tasks"]:
        path = EVIDENCE / f"v17_youtube_dl_bugsinpy_{task['bug_id']}.json"
        if not path.is_file():
            items.append({"id": task["id"], "status": "not_run"})
            continue
        raw = path.read_bytes()
        entry = json.loads(raw)
        if entry["protocol_sha256"] != expected or entry["id"] != task["id"]:
            raise ValueError("mismatched task provenance: " + task["id"])
        item = {"id": task["id"], "status": entry["status"],
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "eligible": bool(entry.get("prevalidation") and
                                 entry["prevalidation"].get("eligible"))}
        if entry["status"] == "completed":
            arms = {a["arm"]: a for a in entry["arms"]}
            if len(entry["arms"]) != 2 or set(arms) != {"baseline", "nykra"}:
                raise ValueError("paired arm results missing")
            item["arms"] = {}
            for arm in ("baseline", "nykra"):
                a = arms[arm]
                item["arms"][arm] = {
                    "passed": a["regression_test_passed"],
                    "attempts": a["attempts_used"],
                    "model_calls_ok": sum(x["model_status"] == "ok" for x in a["attempts"]),
                    "tokens_reported": a["tokens_reported"],
                    "model_seconds": a["total_model_seconds"],
                    "branch_resets": sum(x["kind"] == "new_root" and i > 0
                                         for i, x in enumerate(a["attempts"])),
                }
        else:
            item["eligibility_statuses"] = {
                k: v["status"] for k, v in (entry.get("prevalidation") or {}).items()
                if isinstance(v, dict) and "status" in v
            }
        items.append(item)
    outstanding = [x["id"] for x in items if x["status"] not in
                   ("completed", "infrastructure_excluded")]
    if require_complete and outstanding:
        raise ValueError("unfinished registered tasks: " + ",".join(outstanding))
    done = [x for x in items if x["status"] == "completed"]
    wins = {arm: sum(x["arms"][arm]["passed"] for x in done)
            for arm in ("baseline", "nykra")}
    better = sum(x["arms"]["nykra"]["passed"] and not x["arms"]["baseline"]["passed"]
                 for x in done)
    worse = sum(x["arms"]["baseline"]["passed"] and not x["arms"]["nykra"]["passed"]
                for x in done)
    discordant = better + worse
    p = (math.fsum(math.comb(discordant, k) / 2 ** discordant
                   for k in range(better, discordant + 1))
         if discordant else 1.0)
    return {
        "schema": "nykra-real-bugsinpy-pilot-report-v1",
        "protocol_sha256": expected,
        "model": manifest["model"],
        "registered": len(items),
        "paired_complete": len(done),
        "excluded": sum(x["status"] == "infrastructure_excluded" for x in items),
        "unfinished": outstanding,
        "task_successes": wins,
        "nykra_only_wins": better,
        "baseline_only_wins": worse,
        "paired_one_sided_exact_p": p,
        "official_swebench": False,
        "separate_hidden_verifier": False,
        "general_coding_agent_improvement_proven": False,
        "causal_uplift_established": False,
        "tasks": items,
    }


def save_summary():
    data = summarize(require_complete=True)
    dest = EVIDENCE / "v17_external_pilot_summary.json"
    if dest.exists():
        raise ValueError("refusing to overwrite recorded evidence")
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return dest
