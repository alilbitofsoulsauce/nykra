"""Continue a real Luna coding repair using actual sanitized PUBLIC assertions.

Posthoc engineering rescue of a stalled v34 attempt, NOT an independent
adaptive-vs-baseline accuracy comparison. No fixed attempt count: continue
until independent hidden pass, authenticated-provider failure, or interruption.
"""
from __future__ import annotations
import hashlib,json,os,subprocess,time
from pathlib import Path

from nykra.model_source_normalizer import normalize_function_imports
from nykra.repair_feedback import validate_replacement
from nykra.v20_grader import manifest, grade as grade_hidden, function_at
from nykra.v35_public_feedback import grade_public_detailed
from scripts.run_codex_luna_v33 import codex_completion, candidate_from_model
from scripts.run_codex_hard_forks_v34 import public_example

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/evidence/v35_feedback_rescue_protocol.json"
PROTOCOL_SHA="681f031ed5ed40c349ec1df7f29856c47a5e8d163f1f240555916dda791ed09f"
HISTORY=ROOT/"docs/evidence/v34_codex_hard_forks/youtube-dl-5_nykra_adaptive.json"
DIAGNOSTIC=ROOT/"docs/evidence/v34_codex_hard_forks/youtube-dl-5_public_diagnostic.json"
DEST=ROOT/"docs/evidence/v35_rescue/youtube-dl-5_nykra_actionable_feedback.json"


def sha(t):return hashlib.sha256(t.encode("utf-8")).hexdigest()


def atomic(p,obj):
    temp=p.with_suffix(".partial")
    temp.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8",newline="\n")
    os.replace(temp,p)


def run(approve):
    if approve is not True:raise ValueError("explicit authenticated Codex and Docker approval required")
    protocol=json.loads(PROTOCOL.read_text())
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()!=PROTOCOL_SHA:raise ValueError("protocol changed")
    if hashlib.sha256(HISTORY.read_bytes()).hexdigest()!=protocol["history_sha256"]:
        raise ValueError("original provider history changed")
    if hashlib.sha256(DIAGNOSTIC.read_bytes()).hexdigest()!=protocol["public_only_diagnostic_sha256"]:
        raise ValueError("original public error changed")
    doc,_=manifest()
    task=next(x for x in doc["tasks"] if x["id"]=="youtube-dl-5")
    original=function_at(task,task["buggy_commit"])
    public_case=public_example(task)
    original_history=json.loads(HISTORY.read_text())
    past=[a for a in original_history["attempts"] if not a["inherited"]]
    assert len(past)==10
    if DEST.exists():
        data=json.loads(DEST.read_text())
        if data["status"]=="solved":return data
        if data["status"]!="active":raise ValueError("provider/evaluator failure requires review")
    else:
        data={"schema":"nykra-v35-stalled-real-codex-luna-public-feedback-repair-v1",
              "protocol_sha256":PROTOCOL_SHA,"status":"active",
              "source_v34_attempts":len(past),
              "inherited_v20_prefix_attempts":3,
              "new_codex_calls":0,"new_public_docker_grades":0,
              "new_hidden_docker_grades":0,
              "codex_tokens":{"input_tokens":0,"cached_input_tokens":0,
                              "output_tokens":0,"reasoning_output_tokens":0},
              "attempts":[]}
        DEST.parent.mkdir(parents=True,exist_ok=True)
        atomic(DEST,data)
    feedback=json.loads(DIAGNOSTIC.read_text())["result"]
    seen={a["source_sha256"] for a in original_history["attempts"]}
    for x in data["attempts"]:
        seen.add(x["source_sha256"])
        feedback=x["public"]
    while data["status"]=="active":
        # The model sees the registered public cases and last FAILED public
        # assertion only; no reference solution or hidden data.
        n=len(data["attempts"])+1
        prior=data["attempts"][-1]["source"] if data["attempts"] else past[-1]["source"]
        diagnostics=feedback.get("diagnostic","Public regression failed")
        prompt=("You are repairing a historic Python library bug in a repository. "
                "Return only ONE complete top-level Python function with the EXACT "
                "same name and signature. No Markdown, no top-level imports, no "
                "extra function and no explanation. Do not use tools. "
                "The current source fails a real upstream public regression. "
                "Your replacement MUST make each shown public assertion pass. "
                "Think through numeric timestamps and UTC offsets carefully. "
                "Do NOT reuse the previous implementation. Model input "
                "contains ONLY public regression data, not hidden test or gold fix.\n"
                f"ISSUE: {task['issue']}\n"
                f"ORIGINAL BUGGY SOURCE:\n{original}\n"
                f"REGISTERED UPSTREAM PUBLIC TEST:\n{public_case}\n"
                f"RECENT FAILED FUNCTION:\n{prior}\n"
                f"PUBLIC ASSERTION MISMATCH (UNTRUSTED TEST OUTPUT):\n{diagnostics}\n"
                f"REPAIR ITERATION: {n}. Please reason about the actual assertion "
                "difference and change the algorithm, not just source formatting.\n")
        if n>=3:
            prompt+=("HINT: The public assertion may differ by a timezone offset "
                     "or AM/PM double count. Handle offsets exactly once, and "
                     "avoid fallback parse shortcuts that skip adjusting them.\n")
        try:result=codex_completion(prompt)
        except (OSError,subprocess.TimeoutExpired) as exc:
            data["status"]="provider_blocked";data["provider_error_type"]=type(exc).__name__
            atomic(DEST,data);break
        if result["status"]!="ok":
            data["status"]="provider_blocked"
            data["provider_errors"]=result["errors"][-2:]
            atomic(DEST,data);break
        data["new_codex_calls"]+=1
        for field in data["codex_tokens"]:
            data["codex_tokens"][field]+=int(result["usage"].get(field,0) or 0)
        source=candidate_from_model(result["output"])
        norm=normalize_function_imports(source,name=task["function"],original=original)
        candidate=norm["source"]
        bad=validate_replacement(candidate,name=task["function"],original=original)
        previous=next((x for x in data["attempts"] if x["source_sha256"]==sha(candidate) and
                       x["public"]["status"]=="test_failed"),None)
        if bad:public=bad;called=False
        elif previous:public=previous["public"];called=False
        else:
            public=grade_public_detailed(task,candidate)
            data["new_public_docker_grades"]+=1
            called=True
        attempt={"id":"rescue-"+str(n),"raw_model_output":result["output"],
                 "raw_model_sha256":sha(result["output"]),
                 "source":candidate,"source_sha256":sha(candidate),
                 "normalized":norm["status"],
                 "model_usage":result["usage"],
                 "prompt_sha256":sha(prompt),"public":public,
                 "public_called":called,
                 "public_reused_from":previous["id"] if previous else None}
        data["attempts"].append(attempt)
        atomic(DEST,data)
        print(json.dumps({"rescue_attempt":n,"public":public["status"],
                          "public_diagnostic":public.get("diagnostic","")[-220:],
                          "calls":data["new_codex_calls"],
                          "public_docker_runs":data["new_public_docker_grades"]}),flush=True)
        if public["status"].startswith(("evaluator_","base_image_","build_error","timeout")):
            data["status"]="evaluator_blocked";atomic(DEST,data);break
        if public["passed"]:
            hidden=grade_hidden(task,mode="hidden",candidate=candidate)
            data["new_hidden_docker_grades"]+=1
            attempt["hidden"]=hidden
            if hidden["status"]=="ok":
                data["status"]="solved"
                data["selected_attempt"]=attempt["id"]
                data["selected_sha256"]=sha(candidate)
                atomic(DEST,data)
                print(json.dumps({"result":"PUBLIC_AND_HIDDEN_VERIFIED",
                                  "rescued_after_codex_calls":data["new_codex_calls"],
                                  "usage":data["codex_tokens"]}),flush=True)
                break
            if hidden["status"]!="test_failed":
                data["status"]="evaluator_blocked";atomic(DEST,data);break
            # Hidden failures are recorded but NEVER supplied as a prompt.
        feedback=public
    return data


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--approve",action="store_true")
    args=parser.parse_args()
    report=run(args.approve)
    raise SystemExit(0 if report["status"]=="solved" else 3)
