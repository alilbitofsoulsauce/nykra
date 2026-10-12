"""Real Python repository-code regression pilot using Codex as an inference-only agent.

The task modules are copied from the real Nykra Git checkout and each receives
one deliberately injected bug in a fresh disposable Git repository. Codex
proposes an AST-validated replacement for only the target function. The host
owns patching and testing; the model has no write/tool access or hidden tests.

This is NOT an external repository issue benchmark, not an OS-hardened sandbox,
and it has NO inference across agents or recursive self-improvement claims.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

from .native_codex_pilot import MODEL, RUNNER

PROTOCOL_FILE = Path(__file__).resolve().parents[1] / "docs/evidence/v15_repo_pilot_protocol.json"
REGRESSIONS = {
    "pvalue-tail": ("range(improved,n+1)", "range(improved+1,n+1)"),
    "wall-connectivity": ("and nxt not in walls and nxt not in seen", "and nxt not in seen"),
    "bootstrap-quantile": ("int(reps*0.975)", "int(reps*0.85)"),
    "finite-scores": ("or not math.isfinite(value)", ""),
    "identifier-validation": ("if not re.fullmatch(", "if re.fullmatch("),
    "driver-capabilities": (
        'autonomous_generation=False, auto_policy_application=False,\n            implementation="discovery_only"',
        'autonomous_generation=True, auto_policy_application=False,\n            implementation="discovery_only"',
    ),
}
SCHEMA = {"type": "object", "properties": {"source": {"type": "string"}},
          "required": ["source"], "additionalProperties": False}
TEST_RUNNER = r'''
import importlib, json, math, sys
from unittest.mock import patch
root = sys.argv[1]
module_name = sys.argv[2]
function_name = sys.argv[3]
sys.path.insert(0, root)
mod = importlib.import_module(module_name)
fn = getattr(mod, function_name)
data = json.load(sys.stdin)
results = []
def restore(value):
    if isinstance(value, dict) and set(value) == {"$float"}:
        return {"nan": float("nan"), "inf": float("inf"), "-inf": -float("inf")}[value["$float"]]
    if isinstance(value, list):
        return [restore(x) for x in value]
    return value
for args in data:
    try:
        if function_name == "scan_drivers":
            present = set(args["which"])
            with patch("nykra.drivers.shutil.which", side_effect=lambda command: ("runner" if command in present else None)):
                scan = fn(relai_database_detected=False)
            value = [[x["id"], x["detected"], x["autonomous_generation"],
                      x["auto_policy_application"]] for x in scan["drivers"]]
        elif function_name == "_bootstrap_interval":
            value = fn(restore(args[0]), **args[1]["$kwargs"])
        else:
            value = fn(*restore(args))
        results.append({"value": value})
    except Exception as error:
        results.append({"error":type(error).__name__})
print(json.dumps(results, allow_nan=False))
'''


def protocol() -> dict:
    config = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    assert config["id"] == "nykra-git-regression-pilot-v1"
    assert config["model"] == MODEL
    assert config["max_model_turns_per_task_arm"] == 2
    assert {x["id"] for x in config["tasks"]} == set(REGRESSIONS)
    assert all(sorted(x["order"]) == ["baseline", "nykra"] for x in config["tasks"])
    return config


def extract_function(content: str, name: str) -> str:
    tree = ast.parse(content)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == name]
    if len(matches) != 1:
        raise ValueError("target function must occur exactly once")
    node = matches[0]
    lines = content.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno])


def replace_function(content: str, name: str, proposed: str) -> str:
    if not isinstance(proposed, str) or len(proposed.encode("utf-8")) > 10000:
        raise ValueError("source missing or exceeds 10KB")
    parsed = ast.parse(proposed)
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.FunctionDef):
        raise ValueError("expected exactly one top-level function")
    node = parsed.body[0]
    if node.name != name or node.decorator_list:
        raise ValueError("function name or decorator invalid")
    lines = content.splitlines(keepends=True)
    original = ast.parse(content)
    nodes = [x for x in original.body if isinstance(x, ast.FunctionDef) and x.name == name]
    if len(nodes) != 1:
        raise ValueError("target missing")
    target = nodes[0]
    proposed = proposed.rstrip("\r\n") + "\n\n"
    rebuilt = "".join(lines[:target.lineno-1]) + proposed + "".join(lines[target.end_lineno:])
    compile(rebuilt, name, "exec")
    return rebuilt


def prepare_repository(task: dict, parent_dir: Path, *, mutate: bool = True) -> Path:
    source = Path(__file__).resolve().parents[1]
    destination = parent_dir / ("checkout-buggy" if mutate else "checkout-original")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / "nykra", destination / "nykra", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(source / "tests", destination / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(source / "pyproject.toml", destination / "pyproject.toml")
    # Never copy user auth records, Nykra live state or hidden verdict data.
    if mutate:
        file = destination / task["file"]
        raw = file.read_text(encoding="utf-8")
        old_text = extract_function(raw, task["function"])
        before, after = REGRESSIONS[task["id"]]
        if old_text.count(before) != 1:
            raise ValueError(f"expected exactly one mutation location for {task['id']}")
        changed = old_text.replace(before, after, 1)
        assert changed != old_text
        file.write_text(replace_function(raw, task["function"], changed), encoding="utf-8")
    commands = [
        ["git", "init", "-q"], ["git", "add", "-A"],
        ["git", "-c", "user.name=Nykra Experiment",
         "-c", "user.email=benchmark@localhost", "commit", "-qm", "Frozen start"],
    ]
    for command in commands:
        # Staging may exceed 12 seconds under Windows CI disk/antivirus load.
        # Keep the operation bounded while allowing slower fresh-clone hosts.
        timeout = 60 if command[:2] == ["git", "add"] else 12
        result = subprocess.run(command, cwd=destination, capture_output=True,
                                text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError("disposable Git setup failed")
    return destination


def expected_outcomes(task_id: str, *, heldout: bool) -> tuple[list, list]:
    rng = random.Random("v15-hidden:" + task_id if heldout else "v15-train:" + task_id)
    count = 26 if heldout else 7
    args = []
    expected = []
    def record(arguments, outcome):
        args.append(arguments)
        expected.append(outcome)
    if task_id == "pvalue-tail":
        for a,b in [(0,0),(5,0),(0,5),(2,2)] + [
            (rng.randint(0,18),rng.randint(0,18)) for _ in range(count-4)]:
            n=a+b
            p = math.fsum(math.comb(n,k)/2**n for k in range(a,n+1)) if n else 1.0
            record([a,b], {"value":p})
    elif task_id == "wall-connectivity":
        for i in range(count):
            size=rng.randint(3,6)
            start=[0,0];end=[size-1,size-1]
            walls=[]
            if i%3==0:
                walls=[[1,y] for y in range(size)]
            else:
                walls=[[x,y] for x in range(size) for y in range(size)
                       if [x,y] not in (start,end) and rng.random() < (.16 if i%3 else .4)]
            board={"width":size,"height":size,"start":start,"goal":end,"walls":walls}
            blocks={tuple(k) for k in walls}
            frontier=[tuple(start)];visited={tuple(start)}
            while frontier:
                a,b=frontier.pop(0)
                for xx,yy in ((a+1,b),(a-1,b),(a,b+1),(a,b-1)):
                    if 0<=xx<size and 0<=yy<size and (xx,yy) not in blocks and (xx,yy) not in visited:
                        visited.add((xx,yy));frontier.append((xx,yy))
            record([board],{"value":tuple(end) in visited})
    elif task_id == "bootstrap-quantile":
        for i in range(count):
            deltas=[rng.choice([-2,-1,0,0,1,2]) for _ in range(rng.randint(5,12))]
            seed=rng.randrange(1,500000)
            reps=200 if heldout else 100
            sample_rng=random.Random(seed^0x5F3759DF)
            means=sorted(sum(deltas[sample_rng.randrange(len(deltas))] for _ in deltas)/len(deltas)
                         for _ in range(reps))
            lower=round(means[int(reps*0.025)],5)
            upper=round(means[min(reps-1,int(reps*0.975))],5)
            record([deltas,{"$kwargs":{"seed":seed,"reps":reps}}],{"value":[lower,upper]})
    elif task_id == "finite-scores":
        values=[0,1,-4,2.2,True,"3",{"$float":"nan"},{"$float":"inf"},{"$float":"-inf"}]
        values += [rng.uniform(-1e5,1e5) for _ in range(count-len(values))]
        for value in values[:count]:
            if isinstance(value,(dict,str,bool)):
                record([value],{"error":"NykraError"})
            else:
                record([value],{"value":float(value)})
    elif task_id == "identifier-validation":
        words=["alpha","run/v1","agent:id","_x","abc.xyz","bad name","bad#id","hello!","",
               "   tag   ","a"*257]
        words += [rng.choice(["tool","model","nykra"]) + rng.choice([".","@","#","!","/"," ","-"]) + str(i)
                  for i in range(count-len(words))]
        import re
        for word in words[:count]:
            val=word.strip()
            valid=bool(val and len(val)<=256 and re.fullmatch(r"[a-zA-Z0-9_./:@-]+",val))
            record([word,"candidate"],{"value":val} if valid else {"error":"NykraError"})
    elif task_id == "driver-capabilities":
        subset=[[],["codex"],["opencode"],["codex","opencode","gemini"],
                ["claude","cursor"],["codex","claude","opencode","gemini","cursor"]]
        for i in range(count):
            present=set(subset[i%len(subset)])
            ids=["relai","codex","claude","opencode","gemini","cursor"]
            record({"which":list(present)},{"value":[[x,x in present,False,False]
                   for x in ids]})
    else:
        raise KeyError(task_id)
    return args,expected


def grade(repo: Path, task: dict, *, heldout: bool) -> dict:
    arguments, expected=expected_outcomes(task["id"],heldout=heldout)
    module=task["file"].replace("/",".").removesuffix(".py")
    request=json.dumps(arguments,ensure_ascii=False,allow_nan=False)
    environment={key:value for key,value in os.environ.items()
                 if key in ("SYSTEMROOT","WINDIR","PATH","TEMP","TMP")}
    environment["PYTHONIOENCODING"]="utf-8"
    try:
        result=subprocess.run(
            [sys.executable,"-I","-B","-c",TEST_RUNNER,str(repo),module,task["function"]],
            input=request, stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding="utf-8",errors="replace",cwd=repo,env=environment,timeout=9)
        if result.returncode or len(result.stdout)>200000:
            raise RuntimeError("test subprocess returned nonzero")
        actual=json.loads(result.stdout)
        if not isinstance(actual,list) or len(actual)!=len(expected):
            raise ValueError("invalid grader response")
    except Exception:
        return {"passed":0,"total":len(expected),"score":0.,"status":"execution_failed",
                "failed_public":[]}
    passed=0
    failures=[]
    for inputs, exp, got in zip(arguments,expected,actual):
        if got==exp or ("value" in exp and "value" in got
                        and isinstance(exp["value"],float) and isinstance(got["value"],float)
                        and math.isclose(exp["value"],got["value"],rel_tol=1e-12,abs_tol=1e-12)):
            passed+=1
        elif not heldout and len(failures)<3:
            failures.append({"inputs":inputs,"expected":exp,"observed":got})
    return {"passed":passed,"total":len(expected),"score":passed/len(expected),
            "status":"ok","failed_public":failures}


def model_prompt(task:dict, source:str, *, prev:dict|None, arm:str)->str:
    shared=(
        "You are repairing one genuine Nykra Python repository function in an "
        "isolated Git checkout. Output JSON only: {\"source\": \"<entire corrected "
        "def FUNCTION(...)>\"}. Use ordinary valid Python; no artificial AST "
        "restrictions on methods or standard libraries. Do not read local files "
        "or call tools. The host will patch ONLY the named function and run "
        "independent tests. Preserve the exact function signature and public API."
        "\nFILE: "+task["file"]+"\nFUNCTION: "+task["function"]
        +"\nREPORTED BUG:\n"+task["bug"]
        +"\nCURRENT REGRESSION FUNCTION:\n"+source
    )
    if prev is None:
        return shared+"\nReturn a complete replacement function as JSON."
    shared+=("\nPREVIOUS CANDIDATE:\n"+(prev.get("source") or "(no source)")
             +"\nPUBLIC TEST FEEDBACK:\n"+json.dumps(prev["public"],ensure_ascii=False)
             +"\nPATCH OR VALIDATION ERROR: "+(prev.get("error") or "none"))
    if arm=="nykra":
        return shared+"\nNYKRA POLICY: incrementally revise the previous evaluated candidate, focusing on failed cases while preserving passing behavior. Return the full corrected function."
    return shared+"\nBASELINE POLICY: generate a fresh independent replacement from the bug requirements, using the same prior patch and test feedback. Return the full corrected function."


def invoke_codex(prompt:str,*,timeout:int)->dict:
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-repopatch-codex-") as directory:
        root=Path(directory)
        (root/"schema.json").write_text(json.dumps(SCHEMA),encoding="utf-8")
        outfile=root/"result.json"
        command=[str(RUNNER),"exec","--ignore-user-config","--sandbox","read-only",
                 "--skip-git-repo-check","--model",MODEL,
                 "-c",'approval_policy="never"',"-c",'model_reasoning_effort="low"',
                 "--output-schema",str(root/"schema.json"),
                 "--output-last-message",str(outfile),prompt]
        try:
            result=subprocess.run(command,cwd=root,stdin=subprocess.DEVNULL,
                                  capture_output=True,text=True,encoding="utf-8",
                                  errors="replace",timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status":"model_timeout","source":None,"seconds":round(time.monotonic()-start,2),
                    "tokens":None}
        except OSError:
            return {"status":"model_start_error","source":None,"seconds":round(time.monotonic()-start,2),
                    "tokens":None}
        tokens=re.findall(r"tokens used\s*\n([\d,]+)",result.stderr)
        used=int(tokens[-1].replace(",","")) if tokens else None
        outcome={"status":"model_failed","source":None,
                 "seconds":round(time.monotonic()-start,2),"tokens":used}
        if result.returncode or not outfile.exists():
            return outcome
        try:
            obj=json.loads(outfile.read_text(encoding="utf-8"))
            source=obj["source"]
            if set(obj)!={"source"} or not isinstance(source,str):
                return outcome
            outcome.update(status="ok",source=source,
                           source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest())
        except (ValueError,KeyError,TypeError):
            return outcome
        return outcome


def run_arm(task:dict,arm:str,baseline_repo:Path,*,timeout:int)->dict:
    original_file=baseline_repo/task["file"]
    original_text=original_file.read_text(encoding="utf-8")
    broken_function=extract_function(original_text,task["function"])
    attempts=[]
    for iteration in (1,2):
        parent=attempts[-1] if attempts else None
        if parent and parent["public"]["passed"]==parent["public"]["total"]:
            break
        prompt=model_prompt(task,broken_function,prev=parent,arm=arm)
        model=invoke_codex(prompt,timeout=timeout)
        code=model.get("source")
        error=None
        if code is None:
            evaluation={"passed":0,"total":7,"score":0.,"status":"model_no_candidate","failed_public":[]}
        else:
            try:
                changed=replace_function(original_text,task["function"],code)
                original_file.write_text(changed,encoding="utf-8")
                evaluation=grade(baseline_repo,task,heldout=False)
            except (SyntaxError,ValueError,UnicodeError) as exc:
                error=type(exc).__name__+": "+str(exc)[:180]
                evaluation={"passed":0,"total":7,"score":0.,"status":"patch_invalid","failed_public":[]}
        # Store diff and source, including failed candidate attempts, outside live DB.
        diff=subprocess.run(["git","diff","--",task["file"]],cwd=baseline_repo,
                            capture_output=True,text=True,encoding="utf-8",
                            errors="replace",timeout=8).stdout
        attempts.append({**model,"error":error,"attempt":iteration,
                         "public":evaluation,"diff":diff,"parent":iteration-1 if arm=="nykra" and iteration>1 else None})
        original_file.write_text(original_text,encoding="utf-8")
    valid=[a for a in attempts if a.get("source") is not None and a["public"]["status"]=="ok"]
    best=max(valid,key=lambda a:(a["public"]["score"],-a["attempt"])) if valid else None
    if best:
        original_file.write_text(replace_function(original_text,task["function"],best["source"]),encoding="utf-8")
        hidden=grade(baseline_repo,task,heldout=True)
        final_diff=subprocess.run(["git","diff","--",task["file"]],cwd=baseline_repo,
                                  capture_output=True,text=True,timeout=8).stdout
    else:
        hidden={"passed":0,"total":26,"score":0.,"status":"no_valid_patch","failed_public":[]}
        final_diff=""
    original_file.write_text(original_text,encoding="utf-8")
    return {
        "arm":arm,"task":task["id"],"attempts_used":len(attempts),
        "selected_attempt":best["attempt"] if best else None,
        "hidden_passed":hidden["passed"],"hidden_total":hidden["total"],
        "fully_solved":hidden["score"]==1.,
        "reported_tokens":sum(a.get("tokens") or 0 for a in attempts),
        "token_reporting_complete":all(a.get("tokens") is not None for a in attempts),
        "model_seconds":round(sum(a["seconds"] for a in attempts),2),
        "final_diff":final_diff,"attempts":attempts,
    }


def execute_task(task_id:str,output:Path,*,approval:bool=False)->dict:
    if approval is not True:
        raise ValueError("explicit approval needed for model actions")
    doc=protocol()
    task=next((x for x in doc["tasks"] if x["id"]==task_id),None)
    if task is None:
        raise ValueError("unregistered task")
    if output.exists():
        raise ValueError("refusing to overwrite study result")
    pb=PROTOCOL_FILE.read_bytes()
    output.parent.mkdir(parents=True,exist_ok=True)
    row={"protocol":doc["id"],"protocol_sha256":hashlib.sha256(pb).hexdigest(),
         "task_id":task_id,"model":MODEL,"state":"running","arms":[]}
    def save():
        part=output.with_suffix(".partial")
        part.write_text(json.dumps(row,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        os.replace(part,output)
    save()
    with tempfile.TemporaryDirectory(prefix="nykra-repo-repair-") as home:
        folder=Path(home)
        repo=prepare_repository(task,folder)
        hidden_good=grade(repo,task,heldout=True)
        public_bad=grade(repo,task,heldout=False)
        # Current injected bug must demonstrably fail on public and hidden cases.
        if hidden_good["score"]>=1 or public_bad["score"]>=1:
            raise ValueError("incorrect task fixture: broken baseline passes")
        for arm in task["order"]:
            result=run_arm(task,arm,repo,timeout=doc["max_seconds_per_model_turn"])
            row["arms"].append(result);save()
    row["state"]="completed";save()
    return row


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--task",required=True,choices=sorted(REGRESSIONS))
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--approve",action="store_true")
    args=parser.parse_args()
    result=execute_task(args.task,args.out,approval=args.approve)
    for arm in result["arms"]:
        print(result["task_id"],arm["arm"],arm["hidden_passed"],arm["hidden_total"])
