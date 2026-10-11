"""v0.21 standalone, pinned, constrained real-upstream repair grader.

Immutable v0.20 behavior is left untouched. The candidate is checked with
repair_feedback before Docker; public failure diagnostics are minimal and
sanitized. Hidden stderr and cases NEVER enter model-facing results.
"""
from __future__ import annotations
import hashlib,json,re,subprocess,tempfile,time,uuid
from pathlib import Path

from .v20_grader import ROOT,EVIDENCE,export,_git,function_at,IMAGE_TAG
from .v21_hidden_spec import HIDDEN_TEST_MODULES
from .repair_feedback import safe_feedback,validate_replacement

PROTOCOL=EVIDENCE/"v21_protocol.json"

def manifest():
    raw=PROTOCOL.read_bytes()
    doc=json.loads(raw)
    if doc["id"]!="nykra-v21-actionable-public-feedback-v1":
        raise ValueError("unrecognized v21 protocol")
    if hashlib.sha256(Path(__file__).with_name("v21_hidden_spec.py").read_bytes()).hexdigest()!=doc["hidden_spec_sha256"]:
        raise ValueError("hidden cases changed after freeze")
    if len(doc["tasks"])!=doc["count"] or len({t["id"] for t in doc["tasks"]})!=doc["count"]:
        raise ValueError("protocol count mismatch")
    if not all(t["id"] in HIDDEN_TEST_MODULES and t["project"]=="youtube-dl" for t in doc["tasks"]):
        raise ValueError("unregistered case")
    return doc,hashlib.sha256(raw).hexdigest()

def _commands(t,mode):
    if mode=="public":
        return [["-B","-m","unittest","-q",t["public_test"]]]
    if mode!="hidden":
        raise ValueError("unknown grading mode")
    return [["-B","-m","unittest","-q","_nykra_v21_private_checks"]]+[
        ["-B","-m","unittest","-q",x] for x in t["hidden_upstream_tests"]]

def _prepare(task,root:Path,replacement):
    from .repository_repair_trial import replace_function
    export(task,root)
    file=root/task["test_file"]
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(_git(task,task["fixed_commit"],task["test_file"]))
    (root/"_nykra_v21_private_checks.py").write_text(
        HIDDEN_TEST_MODULES[task["id"]],encoding="utf-8")
    if replacement is not None:
        src=root/task["source_file"]
        src.write_text(replace_function(src.read_text(encoding="utf-8"),
                                         task["function"],replacement),encoding="utf-8")
    (root/"Dockerfile.nykra").write_text(
        "FROM "+IMAGE_TAG+"\nCOPY . /repo\nWORKDIR /repo\n"+
        "ENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\n"+
        "USER 65534:65534\n",encoding="utf-8")
    (root/".dockerignore").write_text(
        ".git\n.env\n.env.*\n**/__pycache__\n**/*.pyc\n",encoding="utf-8")

def grade(task,*,mode,candidate=None):
    protocol,_=manifest()
    if mode not in ("public","hidden"):
        raise ValueError("invalid mode")
    if candidate is not None:
        original=function_at(task,task["buggy_commit"])
        problem=validate_replacement(candidate,name=task["function"],original=original)
        if problem is not None:
            if mode=="hidden":
                return {k:v for k,v in problem.items() if k!="diagnostic"}
            return problem
    tag="nykra-v21-"+uuid.uuid4().hex[:14]
    built=False
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-v21-grader-") as tmp:
        try:
            check=subprocess.run(["docker","image","inspect","--format","{{.Id}}",IMAGE_TAG],
                                 capture_output=True,timeout=16)
            if (check.returncode or check.stdout.decode("ascii","replace").strip()!=
                    protocol["docker_image_id"]):
                return {"status":"evaluator_image_mismatch","passed":False}
            root=Path(tmp)
            _prepare(task,root,candidate)
            build=subprocess.run(["docker","build","--pull=false","--network","none",
                                  "-f",str(root/"Dockerfile.nykra"),"-t",tag,str(root)],
                                  capture_output=True,timeout=90)
            if build.returncode:
                return {"status":"evaluator_build_error","passed":False,
                        "build_stderr_sha256":hashlib.sha256(build.stderr).hexdigest()}
            built=True
            image_inspect=subprocess.run(["docker","image","inspect","--format","{{.Id}}",tag],
                                         capture_output=True,timeout=16)
            image=image_inspect.stdout.decode("ascii","replace").strip()
            if image_inspect.returncode or not re.fullmatch("sha256:[0-9a-f]{64}",image):
                return {"status":"evaluator_image_inspect_error","passed":False}
            records=[]
            for argv in _commands(task,mode):
                command=["docker","run","--rm","--pull","never","--network","none",
                         "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                         "--pids-limit","64","--memory","384m","--memory-swap","384m",
                         "--cpus","1","--user","65534:65534",
                         "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=48m",
                         "--workdir","/repo","--env","PYTHONPATH=/repo",
                         "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1",
                         "--entrypoint","python",image,*argv]
                try:
                    result=subprocess.run(command,capture_output=True,timeout=45)
                except subprocess.TimeoutExpired:
                    records.append({"status":"evaluator_timeout"})
                    break
                if result.returncode==0:
                    status="ok"
                elif result.returncode in (125,126,127) or b"docker: Error response" in result.stderr:
                    status="evaluator_runtime_error"
                else:
                    status="test_failed"
                entry={"status":status,"exit_code":result.returncode,
                       "stdout_sha256":hashlib.sha256(result.stdout).hexdigest(),
                       "stderr_sha256":hashlib.sha256(result.stderr).hexdigest()}
                if mode=="public" and status=="test_failed":
                    entry["diagnostic"]=safe_feedback(
                        result.stderr.decode("utf-8","replace")+"\n"+
                        result.stdout.decode("utf-8","replace"))
                records.append(entry)
                if status!="ok":break
            status=("ok" if len(records)==len(_commands(task,mode))
                    and all(x["status"]=="ok" for x in records)
                    else next((x["status"] for x in records if x["status"]!="ok"),
                              "evaluator_incomplete"))
            ret={"status":status,"passed":status=="ok",
                 "checks":records,"elapsed_seconds":round(time.monotonic()-started,2)}
            if mode=="public" and status=="test_failed":
                ret["diagnostic"]=records[-1].get("diagnostic","Public test failed")
            return ret
        except (OSError,RuntimeError,ValueError,KeyError,SyntaxError,
                UnicodeError,subprocess.TimeoutExpired) as err:
            return {"status":"evaluator_exception","passed":False,
                    "error_type":type(err).__name__}
        finally:
            if built:
                try:subprocess.run(["docker","image","rm","-f",tag],
                                   capture_output=True,timeout=22)
                except (OSError,subprocess.TimeoutExpired):pass

def prevalidate(t):
    original=grade(t,mode="public")
    fixed=function_at(t,t["fixed_commit"])
    ref=grade(t,mode="public",candidate=fixed)
    hidden_original=grade(t,mode="hidden")
    hidden_ref=grade(t,mode="hidden",candidate=fixed)
    out={"public_buggy":original,"public_reference":ref,
         "hidden_buggy":hidden_original,"hidden_reference":hidden_ref}
    out["eligible"]=({k:v["status"] for k,v in out.items()}=={
        "public_buggy":"test_failed","public_reference":"ok",
        "hidden_buggy":"test_failed","hidden_reference":"ok"})
    return out
