"""v36 pre-registered real two-source BugsInPy #35, independently sampled Codex arms."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from nykra.exploration_policy import select_next
from nykra.repair_feedback import public_message
from nykra.v37_multifile_grader import grade, load_protocol, PROTOCOL_SHA, git_blob
from nykra.structured_edit_adapter import exact_edits_to_diff
from nykra.transactional_patch import PatchRejected
from nykra.repair_feedback import safe_feedback
from scripts.run_codex_luna_v33 import codex_completion

ROOT=Path(__file__).resolve().parents[1]
PREFLIGHT=ROOT/"docs/evidence/v37_multifile_preflight.json"
PREFLIGHT_SHA="f98d0a248c82b68210d3ff1b31c5b59b67b71a4df5c939a3f5c3113ba8579912"
OUTPUT=ROOT/"docs/evidence/v37_structured_live"


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


def prompt(task,attempts,action,arm):
    snippets="\n\n".join("FILE "+x["path"]+":\n"+x["buggy_context"]
                           for x in task["buggy_context"])
    common=(
        "Fix the historic upstream NPO extractor JavaScript metadata callback "
        "parsing bug. Modify code only in these permitted source files: "
        +", ".join(task["allowed_production_paths"])+". "
        "The metadata endpoint may return parseMetadata(JSON) followed by a "
        "trailing line comment. Ensure JSONP stripping and the extractor's "
        "metadata source transform both accept this form, while preserving "
        "original cb(JSON) handling. Do not edit tests. "
        "Use the EXACT source context shown below. "
        "The real public and frozen hidden suites run only in restricted Docker.\n"
        "ORIGINAL BUGGY SOURCE CONTEXT:\n"+snippets+
        "\nUPSTREAM PUBLIC TEST CASES:\n"+task["public_excerpt"]+"\n")
    if arm=="baseline_raw_git_diff":
        result=common+(
            "RESPONSE FORMAT: Output only a complete unified Git diff with "
            "diff --git, --- a/path, +++ b/path and @@ hunk headers. "
            "The diff must apply cleanly to the pinned buggy source. "
            "No prose, markdown, code fences or JSON.\n")
    else:
        result=common+(
            "RESPONSE FORMAT: Output ONLY strict JSON in exactly this shape: "
            "{\"edits\":[{\"path\":\"one of allowed files\","
            "\"old\":\"EXACT unique source string\","
            "\"new\":\"replacement source string\"}]}. "
            "Do not output code fences or prose. The old string must match "
            "exactly once in the corresponding ORIGINAL buggy file and can be "
            "a small substring (a single import line or expression). "
            "Use 1-12 small non-overlapping edits, changing both files if "
            "needed; escape newlines and backslashes correctly as JSON. "
            "Nykra will derive all Git diff hunk headers automatically.\n")
    parent=action.get("parent_attempt_id")
    if parent:
        previous=next(x for x in attempts if x["id"]==parent)
        result+=("\nPREVIOUS PROPOSAL FAILED. Revise its algorithm/format; "
                 "ensure exact source correspondence.\n"
                 +previous["raw_codex_output"][:14000]
                 +"\nPUBLIC FEEDBACK:\n"+
                 public_message(previous["public"],enriched=True))
    elif attempts:
        result+=("\nPrevious attempts failed. Solve independently. "
                 "Public feedback: "+
                 public_message(attempts[-1]["public"],enriched=True))
    return result



def run(arm):
    if arm not in ("baseline_raw_git_diff","nykra_structured_adapter"):
        raise ValueError("arm not registered")
    task=load_protocol()
    if sha(PREFLIGHT.read_text(encoding="utf-8"))!=PREFLIGHT_SHA:
        raise ValueError("prevalidated frozen task receipt changed")
    if not json.loads(PREFLIGHT.read_text())["eligible"]:
        raise ValueError("buggy/fixed preflight not eligible")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    path=OUTPUT/("youtube-dl-32_"+arm+".json")
    if path.exists():
        data=json.loads(path.read_text())
        if data["status"]=="hidden_verified":return data
        if data["status"]!="running" or data["protocol_sha256"]!=PROTOCOL_SHA:
            raise ValueError("cannot resume invalid checkpoint")
    else:
        data={"schema":"nykra-v37-structured-edits-vs-raw-git-diff-v1",
              "task":"youtube-dl-32","arm":arm,"model":"gpt-5.6-luna",
              "protocol_sha256":PROTOCOL_SHA,"preflight_sha256":PREFLIGHT_SHA,
              "status":"running","attempts":[],"provider_calls":0,
              "reported_usage":{"input_tokens":0,"cached_input_tokens":0,
                                "output_tokens":0,"reasoning_output_tokens":0},
              "public_docker_calls":0,"public_docker_reuses":0,
              "hidden_docker_calls":0}
        atomic(path,data)
    optimized=arm=="nykra_structured_adapter"
    while data["status"]=="running":
        history=data["attempts"]
        action=select_next(
            policy="depth",
            steps=[{"id":x["id"],"parent_id":x["parent_id"],"position":i,
                    "score":float(x["public"].get("passed",False))}
                   for i,x in enumerate(history)],
            budget=len(history)+1,threshold=1.0)
        if action is None:action={"kind":"new_root","parent_attempt_id":None}
        query=prompt(task,history,action,arm)
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
        transformation=None
        if optimized:
            try:
                originals={path:git_blob(task["buggy_commit"],path)
                           for path in task["allowed_production_paths"]}
                patch,transformation=exact_edits_to_diff(
                    raw,originals=originals,allowed_paths=task["allowed_production_paths"])
                adapter_failure=None
            except PatchRejected as exc:
                patch=""
                adapter_failure=safe_feedback(str(exc))
        else:
            patch=extract_diff(raw)
            adapter_failure=None
        ident=sha(patch)
        previous=next((x for x in history if optimized and
                      x["patch_sha256"]==ident and
                      x["public"]["status"]=="test_failed" and
                      x["public_called"]),None)
        if adapter_failure is not None:
            public={"status":"invalid_patch","passed":False,
                    "diagnostic":adapter_failure,
                    "format_stage":"structured_source_adapter"}
            actual=False
        elif previous:
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
                 "structured_adapter":transformation,
                 "adapter_failure":adapter_failure,
                 "patch":patch,"patch_sha256":ident,
                 "model_usage":completed["usage"],
                 "model_seconds":completed["wall_seconds"],
                 "public":public,"public_called":actual,
                 "public_reused_from":previous["id"] if previous else None}
        history.append(attempt)
        atomic(path,data)
        print(json.dumps({"task":"youtube-dl-32","arm":arm,"attempt":next_id,
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
