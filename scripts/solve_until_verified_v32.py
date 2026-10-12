"""Continue real model-generated upstream repairs until independent hidden verification.

Original v31 history is immutable. This runner resumes it in separate JSON
checkpoints. The public upstream test cases are pre-frozen; hidden evaluator
contents/results are NEVER in any prompt. All candidate source is compiled
and exercised only in pinned restricted Docker via the historical graders.

A session has no arbitrary attempt cap. It exits only on verified solution,
hard provider/evaluator failure, or operator interruption; checkpoints allow
safe continuation. Never commit/push, never promote to original Git source.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from nykra.exploration_policy import select_next
from nykra.model_source_normalizer import normalize_function_imports
from nykra.free_model_client import FreeModelError, generate, generate_cached
from nykra.repair_feedback import validate_replacement, public_message
from nykra.v20_grader import manifest as m20, grade as g20, function_at
from nykra.v21_grader import manifest as m21, grade as g21
from scripts.run_live_efficiency_v31 import candidate_from_model

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/evidence/v32_solve_until_verified_protocol.json"
FROZEN_SHA="06c611da5df7b48143409e1bd477707eacd834c17b21ecf82ce81e8b87b64502"
GRADERS={"v20":(m20,g20),"v21":(m21,g21)}
BAD_INFRA=("evaluator_","base_image_","build_error","setup_error","timeout","image_inspect_error")


def sha(v:str)->str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def initial_history(issue, optimized):
    data=json.loads((ROOT/"docs/evidence/v31_live_issues"/(issue["id"]+".json")).read_text(encoding="utf-8"))
    match="nykra_optimized_depth" if optimized else "baseline_depth"
    arm=next(a for a in data["arms"] if a["arm"]==match)
    assert all(a["public"]["status"]=="test_failed" for a in arm["attempts"])
    assert len(arm["attempts"])==3
    return arm


def prompt(issue,task,original,all_attempts,decision,public_only):
    kind,parent_id=decision["kind"],decision["parent_attempt_id"]
    sequence=len(all_attempts)+1
    seen={x["source_sha256"] for x in all_attempts}
    # Protocol-equal publicly registered spec, never code from the reference fix.
    text=("You are fixing a real historical Python bug. Write ONLY Python source "
          "of ONE complete top-level function definition. Keep the exact same "
          "function name, argument names, signature and defaults. "
          "No markdown, comments outside function, JSON or explanation. "
          "Existing module imports and helper names already work; you may import "
          "standard libraries inside your function. Your objective is to make "
          "the exact public assertions shown below pass, NOT just repeat the "
          "existing buggy function. Think through every shown edge case then "
          "output the full revised function.\n"
          f"ISSUE: {task['issue']}\n"
          f"FUNCTION: {task['function']}\nORIGINAL FUNCTION:\n{original}\n"
          "PUBLIC UPSTREAM REGRESSION TEST (NOT hidden verification):\n"
          +issue["public_test_excerpt"]+"\n"
          +f"MODEL ATTEMPT: {sequence}. ORIGINAL SOURCE HASH: {sha(original)}.\n")
    if parent_id is not None:
        parent=next(x for x in all_attempts if x["id"]==parent_id)
        text+=("NEXT ACTION: REVISE YOUR LAST ATTEMPT.\n"
               "PREVIOUS SOURCE (failed and MUST be changed):\n"+parent["source"]+
               "\nPREVIOUS PUBLIC VERDICT:\n"+public_message(parent["public"],enriched=True)+"\n")
    else:
        text+=("NEXT ACTION: NEW INDEPENDENT ROOT. Do not copy the failed previous "
               "source; derive another algorithm from the public examples.\n"
               "LAST PUBLIC VERDICT:\n"+
               public_message(all_attempts[-1]["public"],enriched=True)+"\n")
    if all_attempts[-1]["source_sha256"] in seen:
        # A repeated patch isn't bad if it is already passing. Here all are failing.
        identical=sum(x["source_sha256"]==all_attempts[-1]["source_sha256"] for x in all_attempts)
        if identical>=2:
            text+=("STALLED CODE DETECTED: Previous model attempts returned exact "
                   "same failing implementation. Changing formatting, string literal "
                   "prefixes or whitespace does not solve the public assertions. "
                   "Derive the output from input examples; rewrite the functional "
                   "logic with a DISTINCT algorithm. A response that reproduces an "
                   "earlier solution without semantic change will be graded as a "
                   "failure and costs an inference call.\n")
    # Task-independent, transparent, increasing diagnostic specificity, shared
    # with BOTH arms at the same number of candidate submissions.
    if sequence>=5:
        text+=("IMPORTANT: For every expected public output, mentally trace "
               "your replacement function on that exact input; if it differs, "
               "fix the branch before replying. Do not merely alter regex style.\n")
    if sequence>=7:
        text+=("ALTERNATIVE IMPLEMENTATION: You may choose a standard-library "
               "parser or simple loop rather than the previous implementation. "
               "For functional iterators, check argument ownership between inner "
               "iteration/wrapping and outer enumerate.\n")
    if sequence>=9:
        text+=("AVOID REPEATED PATCHES: Review whether you are passing a named "
               "argument to the wrong helper or restricting input path depth; "
               "use a different computational technique. Explain nothing in "
               "your response, output source only.\n")
    return text


def atomic(path,document):
    temp=path.with_suffix(".partial")
    temp.write_text(json.dumps(document,indent=2,ensure_ascii=True)+"\n",
                    encoding="utf-8",newline="\n")
    os.replace(temp,path)


def decide(attempts,optimized):
    steps=[{"id":a["id"],"parent_id":a["parent_id"],"score":int(a["public"]["passed"]),
            "position":i} for i,a in enumerate(attempts)]
    return select_next(policy="adaptive" if optimized else "depth",steps=steps,
                       budget=len(steps)+1,threshold=1.0)


def run(issue_name,arm_name,output_root,cache_root,approve):
    if approve is not True:
        raise ValueError("explicit live inference and pinned Docker approval required")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is required; no secret is logged")
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()!=FROZEN_SHA:
        raise ValueError("frozen solve-to-completion protocol digest changed")
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    issue=next((x for x in protocol["issues"] if x["id"]==issue_name),None)
    if issue is None or arm_name not in ("baseline_depth","nykra_adaptive_with_public_reuse"):
        raise ValueError("unrecognized frozen issue or arm")
    optimized=arm_name.startswith("nykra")
    grader_manifest,grader=GRADERS[issue["grader"]]
    doc,_=grader_manifest()
    task=next(x for x in doc["tasks"] if x["id"]==issue_name)
    original=function_at(task,task["buggy_commit"])
    initial=initial_history(issue,optimized)
    output_root.mkdir(parents=True,exist_ok=True)
    save=output_root/(issue_name+"_"+arm_name+".json")
    if save.exists():
        report=json.loads(save.read_text(encoding="utf-8"))
        if report["protocol_sha256"]!=FROZEN_SHA or report["issue"]!=issue_name:
            raise ValueError("checkpoint identity/protocol does not match")
        if report["status"]=="hidden_verified":
            print(json.dumps({"issue":issue_name,"arm":arm_name,"status":"already_solved",
                              "additional_calls":len(report["attempts"])-3}),flush=True)
            return report
        if report["status"] not in ("in_progress","provider_excluded","evaluator_excluded"):
            raise ValueError("unrecognized existing checkpoint status")
        if report["status"]!="in_progress":
            raise ValueError("hard provider/evaluator error; requires operator review")
    else:
        attempts=[]
        for index,a in enumerate(initial["attempts"]):
            # These are the ACTUAL v31 evaluated historical sources and receipts
            # including reported model tokens; do not count replays as new calls.
            attempts.append({"id":f"attempt-{index+1}",
                "parent_id":None if index==0 else f"attempt-{index}",
                "policy_action":"new_root" if index==0 else "revise",
                "source":a["source"],"source_sha256":a["source_sha256"],
                "public":a["public"],"original_v31":True,
                "provider_response_id":a["model_response_id"],
                "provider_tokens":a["model_provider_reported_tokens"],
                "reported_provider_cost":a["model_provider_reported_cost"],
                "public_reused":a["public_grade_reused"],
                "public_reused_from":a["public_grade_source_attempt"],
                "public_docker_called":not a["public_grade_reused"],
                "candidate_prompt_sha256":a["prompt_sha256"]})
        report={"schema":"nykra-v32-solving-session-v1",
                "protocol_sha256":FROZEN_SHA,"issue":issue_name,
                "arm":arm_name,"source_protocol":"v31 historical failed prefix",
                "status":"in_progress","attempts":attempts,
                "hidden_checks_performed":0,"selected_source_sha256":None,
                "model":"cohere/north-mini-code:free",
                "original_three_attempts_provenance_sha256":issue["source_result_sha256"]}
        atomic(save,report)
    attempts=report["attempts"]
    while True:
        if report["status"]=="hidden_verified":
            return report
        # On a passing candidate, check hidden now, but never show its private
        # grading details to subsequent model calls if hidden fails.
        last=attempts[-1]
        if last["public"]["passed"] and not last.get("hidden_checked"):
            hidden=grader(task,mode="hidden",candidate=last["source"])
            report["hidden_checks_performed"]+=1
            last["hidden_checked"]=True
            last["hidden_status"]=hidden["status"]
            last["hidden_receipt"]=hidden
            if hidden["status"]=="ok":
                report["status"]="hidden_verified"
                report["selected_source_sha256"]=last["source_sha256"]
                atomic(save,report)
                print(json.dumps({"issue":issue_name,"arm":arm_name,
                                  "status":"HIDDEN_VERIFIED_SOLVED",
                                  "total_model_calls":len(attempts),
                                  "new_model_calls":len(attempts)-3,
                                  "hidden_receipt":hidden["status"]}),flush=True)
                return report
            if hidden["status"]!="test_failed":
                report["status"]="evaluator_excluded";atomic(save,report)
                raise RuntimeError("hidden grader infra failure, not a model failure")
            # Failed hidden check gets NO diagnostic; only model's public pass is
            # accessible. Generate a fresh independent public-based proposal.
            atomic(save,report)
        decision=decide(attempts,optimized)
        # Following a publicly passing but hidden-failing candidate, score it 0
        # for selecting a next action without leaking private hidden details.
        if decision is None:
            # public may pass but hidden fail; force new_root without hidden logs.
            decision={"kind":"new_root","parent_attempt_id":None}
        query=prompt(issue,task,original,attempts,decision,True)
        number=len(attempts)+1
        before=time.monotonic()
        try:
            if optimized:
                result=generate_cached(query,model=report["model"],max_tokens=1500,
                                       timeout=90,cache_dir=cache_root/issue_name/arm_name,
                                       approve=True)
            else:
                result=generate(query,model=report["model"],max_tokens=1500,
                                timeout=90,approve=True)
        except FreeModelError as err:
            report["status"]="provider_excluded"
            report["provider_error"]=str(err)[:130]
            atomic(save,report)
            raise
        receipt=result["receipt"]
        original_model_source=candidate_from_model(result["text"])
        normalization=normalize_function_imports(
            original_model_source, name=task["function"], original=original)
        generated=normalization["source"]
        digest=sha(generated)
        problem=validate_replacement(generated,name=task["function"],original=original)
        matched=next((x for x in attempts if optimized and x["source_sha256"]==digest
                      and x["public"]["status"]=="test_failed" and x["public_docker_called"]),None)
        if problem:
            public=problem;called=False;reused=False
        elif matched:
            public=matched["public"].copy();called=False;reused=True
        else:
            public=grader(task,mode="public",candidate=generated)
            called=True;reused=False
        item={"id":f"attempt-{number}","parent_id":decision["parent_attempt_id"],
              "policy_action":decision["kind"],"original_v31":False,
              "source":generated,"source_sha256":digest,
              "model_source_original_sha256":sha(original_model_source),
              "normalization_status":normalization["status"],
              "import_statements_moved":normalization["import_statements_moved"],
              "model_raw_output_sha256":sha(result["text"]),
              "model_raw_output":result["text"],
              "candidate_prompt_sha256":sha(query),
              "provider_response_id":receipt.get("response_id"),
              "provider_tokens":receipt["tokens"],
              "reported_provider_cost":receipt["cost"],
              "provider_cache_hit":bool(receipt.get("cache_hit",False)),
              "public":public,"public_docker_called":called,
              "public_reused":reused,
              "public_reused_from":matched["id"] if matched else None,
              "request_plus_public_wall_seconds":round(time.monotonic()-before,3)}
        attempts.append(item)
        atomic(save,report)
        print(json.dumps({"issue":issue_name,"arm":arm_name,"attempt":number,
                          "decision":decision["kind"],
                          "public":public["status"],"docker_called":called,
                          "public_reuse":reused,
                          "tokens":receipt["tokens"].get("total_tokens"),
                          "new_calls":len(attempts)-3}),flush=True)
        if public["status"].startswith(BAD_INFRA):
            report["status"]="evaluator_excluded";atomic(save,report)
            raise RuntimeError("public grader infrastructure excluded")
        # Running until hidden-verified, not a fixed number of failed rounds.


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue",required=True)
    parser.add_argument("--arm",required=True)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--cache-root",type=Path,required=True)
    parser.add_argument("--approve",action="store_true")
    args=parser.parse_args(argv)
    outcome=run(args.issue,args.arm,args.output_root,args.cache_root,args.approve)
    return 0 if outcome["status"]=="hidden_verified" else 3


if __name__=="__main__":
    raise SystemExit(main())
