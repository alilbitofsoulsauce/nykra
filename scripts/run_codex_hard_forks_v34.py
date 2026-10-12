"""Use authenticated native Codex Luna for genuine historical repair until solved.

Two independently sampled arms extend prior 3 already failed real patches.
Sandbox is read-only; generated code executes ONLY in pinned Docker grader.
Persist complete provider and evaluator receipts after each step. No commits.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path

from nykra.exploration_policy import select_next
from nykra.model_source_normalizer import normalize_function_imports
from nykra.repair_feedback import validate_replacement, public_message
from nykra.v20_grader import manifest as m20,grade as g20,function_at,_git
from nykra.v21_grader import manifest as m21,grade as g21
from scripts.run_live_efficiency_v31 import candidate_from_model

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/evidence/v34_codex_hard_forks_protocol.json"
FROZEN="c0c877adde092e4a5a10bcd933dbd82f3ab5505d843b03bcebbc682a56727304"
CODEX=Path.home()/".codex/plugins/.plugin-appserver/codex.exe"
GRADERS={"v20":(m20,g20),"v21":(m21,g21)}
INFRAPREFIX=("evaluator_","base_image_","build_error","setup_error","timeout","image_inspect_error")


def digest(text):return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_task(id_):
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    entry=next((x for x in protocol["tasks"] if x["id"]==id_),None)
    if not entry:raise ValueError("unregistered task")
    manifest,grader=GRADERS["v20"]
    tasks,_=manifest()
    t=next(x for x in tasks["tasks"] if x["id"]==id_)
    return entry,t,grader


def initial_attempts(id_,arm):
    number=id_.split("-")[-1]
    prefix_path=ROOT/("docs/evidence/v20_youtube_dl_"+number+".json")
    original=json.loads(prefix_path.read_text(encoding="utf-8"))
    declared=next(x for x in json.loads(PROTOCOL.read_text())["tasks"] if x["id"]==id_)
    if hashlib.sha256(prefix_path.read_bytes()).hexdigest()!=declared["prefix_sha256"]:
        raise ValueError("pre-frozen historical shared prefix changed")
    attempts=original["shared_prefix"]
    if len(attempts)!=3 or any(x["public"]["status"]!="test_failed" for x in attempts):
        raise ValueError("three failed shared historical prefix not available")
    return [{"id":f"attempt-{i+1}","source":x["source"],
             "source_sha256":x["source_sha256"],
             "parent_id":x["parent_attempt_id"],"public":x["public"],
             "provider":"historical v20 pre-fork Codex",
             "public_called":True,"public_reused":False,"inherited":True}
            for i,x in enumerate(attempts)]


def public_example(t):
    data=_git(t,t["fixed_commit"],t["test_file"]).decode("utf-8",errors="replace")
    method=t["public_test"].split(".")[-1]
    needle="    def "+method+"(self)"
    start=data.index(needle)
    end=data.find("\n    def test_",start+len(needle))
    if end<0:
        end=data.find("\n\nif __name__",start+len(needle))
    if end<0:
        raise ValueError("unable to isolate frozen public method")
    snippet=data[start:end].strip("\n")
    if len(snippet)>4500 or t["function"] not in snippet:
        raise ValueError("unexpected public test excerpt")
    return snippet


def model_prompt(task,broken,public,attempts,action):
    n=len(attempts)+1
    s=("Fix a real historical Python library defect. Reply with ONE complete "
       "Python function definition only, no markdown, preamble, top-level "
       "imports, extra functions or explanation. Keep the original function "
       "name and signature. No tools or file system calls. "
       "The existing module already provides its imports and helpers. "
       "Solve ALL registered public test assertions, without seeing hidden tests.\n"
       f"ISSUE: {task['issue']}\nTARGET: {task['function']}\n"
       f"BUGGY SOURCE:\n{broken}\n"
       f"PUBLIC UPSTREAM TEST CASES:\n{public}\n")
    parent=action["parent_attempt_id"]
    if parent:
        previous=next(a for a in attempts if a["id"]==parent)
        s+=("ACTION: REVISE the failed model patch below. "
            "Use the failed public output to make a semantic change, "
            "not a cosmetic adjustment.\n"
            "FAILED SOURCE:\n"+previous["source"]+"\n"
            +public_message(previous["public"],enriched=True)+"\n")
    else:
        s+=("ACTION: NEW INDEPENDENT SOLUTION from the bug and test examples. "
            "Discard prior approach; propose a separate algorithm.\n"
            "LARGEST PRIOR FAILURE: "+public_message(attempts[-1]["public"],enriched=True)+"\n")
    if n>=5:
        s+=("CHECK: Mentally execute your solution on each shown input. "
            "Fix outputs that differ from expected before replying.\n")
    if n>=7:
        s+=("ALTERNATE APPROACH: Avoid prior failure's regex or iterator argument "
            "assumptions. Try standard-library parsing or explicit steps.\n")
    if n>=9:
        s+=("STAGNATION: The previous attempts have not solved the test. "
            "Choose a genuinely different data transformation.\n")
    return s


def codex_completion(query):
    argv=[str(CODEX),"exec","--skip-git-repo-check","--sandbox","read-only",
          "--json","-m","gpt-5.6-luna","-c",'model_reasoning_effort="low"',query]
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-codex-benchmark-") as tmp:
        run=subprocess.run(argv,cwd=tmp,input="",text=True,capture_output=True,timeout=140)
    events=[]
    for line in run.stdout.splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict):events.append(x)
        except (ValueError,TypeError):pass
    messages=[x["item"]["text"] for x in events if x.get("type")=="item.completed"
              and x.get("item",{}).get("type")=="agent_message"]
    final=next((x for x in reversed(events) if x.get("type")=="turn.completed"),None)
    errors=[x.get("message","") for x in events if x.get("type")=="error"]
    tool_activity=[x.get("item",{}).get("type") for x in events
                   if x.get("type")=="item.completed" and
                   x.get("item",{}).get("type")!="agent_message"]
    response={"status":"ok" if run.returncode==0 and messages and final else "model_error",
              "output":messages[-1] if messages else "",
              "usage":final.get("usage") if final else None,"errors":errors,
              "tool_activity":tool_activity,"exit_code":run.returncode,
              "wall_seconds":round(time.monotonic()-started,3)}
    return response


def save(path,doc):
    tmp=path.with_suffix(".partial")
    tmp.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8",newline="\n")
    os.replace(tmp,path)


def perform(issue,arm,output_dir):
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()!=FROZEN:raise ValueError("frozen protocol changed")
    if arm not in ("baseline_depth","nykra_adaptive"):raise ValueError("unregistered arm")
    if not CODEX.is_file():raise ValueError("native Codex CLI binary unavailable")
    registered,t,grader=load_task(issue)
    code=function_at(t,t["buggy_commit"])
    public=public_example(t)
    output_dir.mkdir(parents=True,exist_ok=True)
    target=output_dir/(issue+"_"+arm+".json")
    if target.exists():
        record=json.loads(target.read_text(encoding="utf-8"))
        if record["status"]=="solved":
            return record
        if record["status"] not in ("active",):raise ValueError("blocked checkpoint requires review")
    else:
        record={"schema":"nykra-v34-codex-luna-real-hard-fork-v1",
                "protocol_sha256":FROZEN,"issue":issue,"arm":arm,
                "provider":"native Codex ChatGPT OAuth","model":"gpt-5.6-luna",
                "initial_3_failures_from_historical_Codex_shared_prefix":True,
                "public_excerpt_sha256":digest(public),"status":"active",
                "attempts":initial_attempts(issue,arm),"hidden_runs":0,
                "codex_completions":0,"codex_reported_usage":{"input_tokens":0,"cached_input_tokens":0,
                                                              "output_tokens":0,
                                                              "reasoning_output_tokens":0}}
        save(target,record)
    attempts=record["attempts"]
    optimized=(arm=="nykra_adaptive")
    while record["status"]=="active":
        next_action=select_next(policy="adaptive" if optimized else "depth",
           steps=[{"id":a["id"],"parent_id":a["parent_id"],"position":i,
                   "score":int(a["public"]["passed"])} for i,a in enumerate(attempts)],
           budget=len(attempts)+1,threshold=1.0)
        if next_action is None:next_action={"kind":"new_root","parent_attempt_id":None}
        prompt=model_prompt(t,code,public,attempts,next_action)
        attemptno=len(attempts)+1
        try:response=codex_completion(prompt)
        except (OSError,subprocess.TimeoutExpired) as exc:
            record["status"]="provider_blocked"
            record["provider_error_type"]=type(exc).__name__;save(target,record);break
        if response["status"]!="ok":
            record["status"]="provider_blocked"
            record["provider_error_summary"]=response["errors"][-1:] or ["missing model completion"]
            record["last_codex_receipt"]=response
            save(target,record);break
        usage=response["usage"]
        for key in record["codex_reported_usage"]:
            record["codex_reported_usage"][key]+=int(usage.get(key,0) or 0)
        record["codex_completions"]+=1
        raw=response["output"]
        original_model_source=candidate_from_model(raw)
        normalized=normalize_function_imports(original_model_source,
                                              name=t["function"],original=code)
        candidate=normalized["source"]
        problem=validate_replacement(candidate,name=t["function"],original=code)
        previous=next((a for a in attempts if optimized
             and a["source_sha256"]==digest(candidate)
             and a["public"]["status"]=="test_failed" and a.get("public_called")),None)
        if problem:
            evaluation=problem; called=False
        elif previous:
            evaluation=previous["public"].copy();called=False
        else:
            evaluation=grader(t,mode="public",candidate=candidate);called=True
        attempt={"id":f"attempt-{attemptno}","inherited":False,
                 "parent_id":next_action["parent_attempt_id"],"policy_action":next_action["kind"],
                 "source":candidate,"source_sha256":digest(candidate),
                 "raw_codex_output":raw,"raw_sha256":digest(raw),
                 "prompt_sha256":digest(prompt),"normalization":normalized["status"],
                 "codex_receipt":{k:v for k,v in response.items() if k!="output"},
                 "public":evaluation,"public_called":called,"public_reused":previous is not None,
                 "public_reused_from":previous["id"] if previous else None}
        attempts.append(attempt)
        save(target,record)
        print(json.dumps({"task":issue,"arm":arm,"attempt":attemptno,
                          "action":next_action["kind"],
                          "public":evaluation["status"],"graded":called,
                          "codex_calls":record["codex_completions"],
                          "tokens":record["codex_reported_usage"]}),flush=True)
        if evaluation["status"].startswith(INFRAPREFIX):
            record["status"]="evaluator_blocked";save(target,record);break
        if evaluation["passed"]:
            hidden=grader(t,mode="hidden",candidate=candidate)
            record["hidden_runs"]+=1
            attempt["hidden_receipt"]=hidden
            save(target,record)
            if hidden["status"]=="ok":
                record["status"]="solved"
                record["selected_id"]=attempt["id"]
                record["selected_sha256"]=attempt["source_sha256"]
                save(target,record)
                print(json.dumps({"task":issue,"arm":arm,"result":"HIDDEN_VERIFIED_SOLVED",
                                  "codex_calls":record["codex_completions"],
                                  "usage":record["codex_reported_usage"]}),flush=True)
                break
            if hidden["status"]!="test_failed":
                record["status"]="evaluator_blocked";save(target,record);break
    return record


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--issue",required=True);p.add_argument("--arm",required=True)
    p.add_argument("--output-dir",type=Path,required=True);p.add_argument("--approve",action="store_true")
    a=p.parse_args()
    if not a.approve:raise ValueError("explicit Codex quota and Docker execution approval required")
    result=perform(a.issue,a.arm,a.output_dir)
    return 0 if result["status"]=="solved" else 3

if __name__=="__main__":
    raise SystemExit(main())
