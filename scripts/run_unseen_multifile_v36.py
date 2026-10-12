"""v36 pre-registered real two-source BugsInPy #35, independently sampled Codex arms."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from nykra.exploration_policy import select_next
from nykra.repair_feedback import public_message
from nykra.v36_multifile_grader import grade, load_protocol, PROTOCOL_SHA
from scripts.run_codex_luna_v33 import codex_completion

ROOT=Path(__file__).resolve().parents[1]
PREFLIGHT=ROOT/"docs/evidence/v36_multifile_preflight.json"
PREFLIGHT_SHA="a7ceb95b1866befed7aeb8cf44c2299d5916bd26070fbd30c43efaf9ccda4c88"
OUTPUT=ROOT/"docs/evidence/v36_multifile_live"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic(path,data):
    temp=path.with_suffix(".partial")
    temp.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8",newline="\n")
    os.replace(temp,path)


def extract_diff(raw):
    text=raw.strip()
    lines=text.splitlines()
    if len(lines)>2 and lines[0] in ("~~~diff","~~~patch","~~~"):
        if lines[-1]=="~~~":
            text="\n".join(lines[1:-1]).strip()
    # The provider may also emit markdown backtick fences.
    if text.startswith(chr(96)*3):
        lines=text.splitlines()
        if lines[-1]==chr(96)*3:
            text="\n".join(lines[1:-1]).strip()
    return text.rstrip()+"\n"


def prompt(task,attempts,action):
    snippets="\n\n".join("FILE "+x["path"]+":\n"+x["buggy_context"]
                         for x in task["buggy_context"])
    # First prompt matches byte-for-byte for both agents.
    query=(
        "Repair the real historical open-source Arte upload date bug. "
        "Return ONLY a complete plain Git unified diff starting with "
        "'diff --git a/PATH b/PATH'. No markdown, explanation, JSON or tools. "
        "Only touch these two production paths: "
        +", ".join(task["allowed_production_paths"])+". "
        "Do not modify tests or add files. "
        "Arte JSON upload date extraction may require use of direct "
        "shooting-date metadata instead of the older VDA fallback, "
        "and date parser must accept day-first datetime with a UTC offset. "
        "Preserve older date cases. Your diff must apply cleanly to the "
        "historic buggy Git source and may touch both modules. "
        "You see ONLY original buggy source snippets and the registered "
        "public regression, never the fixed implementation or hidden tests. "
        "A restricted Docker runner evaluates every proposed source patch.\n"
        "BUGGY CODE CONTEXT:\n"+snippets+
        "\nPUBLIC UPSTREAM TEST CASES:\n"+task["public_excerpt"]+"\n")
    parent=action.get("parent_attempt_id")
    if parent:
        p=next(x for x in attempts if x["id"]==parent)
        query+=("\nREVISE YOUR FAILED PATCH, keep source context exact:\n"+
                p["patch"][:12000]+"\n"+
                public_message(p["public"],enriched=True))
    elif attempts:
        query+=("\nNEW INDEPENDENT ROOT, prior attempts did not yield "
                "a verified repair. Choose a different algorithm.\n"+
                public_message(attempts[-1]["public"],enriched=True))
    return query+"\nReturn a valid diff, ending in newline."


def run(arm):
    if arm not in ("baseline_depth","nykra_adaptive"):
        raise ValueError("arm not registered")
    task=load_protocol()
    if sha(PREFLIGHT.read_text(encoding="utf-8"))!=PREFLIGHT_SHA:
        raise ValueError("prevalidated frozen task receipt changed")
    if not json.loads(PREFLIGHT.read_text())["eligible"]:
        raise ValueError("buggy/fixed preflight not eligible")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    path=OUTPUT/("youtube-dl-35_"+arm+".json")
    if path.exists():
        data=json.loads(path.read_text())
        if data["status"]=="hidden_verified":return data
        if data["status"]!="running" or data["protocol_sha256"]!=PROTOCOL_SHA:
            raise ValueError("cannot resume invalid checkpoint")
    else:
        data={"schema":"nykra-v36-new-upstream-multifile-live-v1",
              "task":"youtube-dl-35","arm":arm,"model":"gpt-5.6-luna",
              "protocol_sha256":PROTOCOL_SHA,"preflight_sha256":PREFLIGHT_SHA,
              "status":"running","attempts":[],"provider_calls":0,
              "reported_usage":{"input_tokens":0,"cached_input_tokens":0,
                                "output_tokens":0,"reasoning_output_tokens":0},
              "public_docker_calls":0,"public_docker_reuses":0,
              "hidden_docker_calls":0}
        atomic(path,data)
    optimized=arm=="nykra_adaptive"
    while data["status"]=="running":
        history=data["attempts"]
        action=select_next(
            policy="adaptive" if optimized else "depth",
            steps=[{"id":x["id"],"parent_id":x["parent_id"],"position":i,
                    "score":float(x["public"].get("passed",False))}
                   for i,x in enumerate(history)],
            budget=len(history)+1,threshold=1.0)
        if action is None:action={"kind":"new_root","parent_attempt_id":None}
        query=prompt(task,history,action)
        try:
            completed=codex_completion(query)
        except (OSError,subprocess.TimeoutExpired) as exc:
            data["status"]="provider_blocked"
            data["provider_error_type"]=type(exc).__name__
            atomic(path,data)
            break
        if completed["status"]!="ok":
            data["status"]="provider_blocked"
            data["provider_errors"]=completed["errors"][-1:]
            atomic(path,data)
            break
        data["provider_calls"]+=1
        for key in data["reported_usage"]:
            data["reported_usage"][key]+=int(completed["usage"].get(key,0) or 0)
        raw=completed["output"]
        patch=extract_diff(raw)
        ident=sha(patch)
        previous=next((x for x in history if optimized and
                      x["patch_sha256"]==ident and
                      x["public"]["status"]=="test_failed" and
                      x["public_called"]),None)
        if previous:
            public=previous["public"].copy()
            data["public_docker_reuses"]+=1
            actual=False
        else:
            public=grade(mode="public",patch=patch)
            actual=public["status"] in ("ok","test_failed","build_error")
            if actual:data["public_docker_calls"]+=1
        next_id="attempt-"+str(len(history)+1)
        attempt={"id":next_id,"parent_id":action["parent_attempt_id"],
                 "policy_action":action["kind"],
                 "prompt_sha256":sha(query),
                 "raw_codex_output":raw,"raw_output_sha256":sha(raw),
                 "patch":patch,"patch_sha256":ident,
                 "model_usage":completed["usage"],
                 "model_seconds":completed["wall_seconds"],
                 "public":public,"public_called":actual,
                 "public_reused_from":previous["id"] if previous else None}
        history.append(attempt)
        atomic(path,data)
        print(json.dumps({"task":"youtube-dl-35","arm":arm,"attempt":next_id,
                          "action":action["kind"],"public":public["status"],
                          "real_public_docker":actual,"provider_calls":data["provider_calls"]}),
              flush=True)
        if public["status"] in ("setup_error","build_error","base_image_mismatch",
                                 "image_inspect_error","evaluator_runtime_error"):
            data["status"]="evaluator_blocked"
            atomic(path,data)
            break
        if public["passed"]:
            hidden=grade(mode="hidden",patch=patch)
            data["hidden_docker_calls"]+=1
            attempt["hidden"]=hidden
            if hidden["status"]=="ok":
                data["status"]="hidden_verified"
                data["selected_patch_sha256"]=ident
                data["selected_attempt"]=next_id
                atomic(path,data)
                print(json.dumps({"result":"PUBLIC_AND_HIDDEN_VERIFIED",
                                  "arm":arm,"provider_calls":data["provider_calls"]}),
                      flush=True)
                break
            if hidden["status"]!="test_failed":
                data["status"]="evaluator_blocked"
                atomic(path,data)
                break
            atomic(path,data)
    return data


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--arm",required=True)
    parser.add_argument("--approve",action="store_true")
    args=parser.parse_args()
    if not args.approve:
        raise ValueError("explicit authenticated Codex and Docker approval required")
    result=run(args.arm)
    raise SystemExit(0 if result["status"]=="hidden_verified" else 3)
