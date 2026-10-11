"""v0.20 Docker-only external real-issue grading, separate private verifier.

Only frozen BugsInPy upstream Git commits, allowlisted source/test paths and
locally pinned evaluator image IDs. Does not execute repo setup/build scripts.
This is restricted Docker containment, NOT a certified malicious-code sandbox.
"""
from __future__ import annotations
import hashlib, io, json, os, re, shutil, subprocess, tarfile, tempfile, time, uuid
from pathlib import Path

from .repository_repair_trial import extract_function, replace_function
from .v20_hidden_spec import HIDDEN_TEST_MODULES

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/evidence"
PROTOCOL=EVIDENCE/"v20_protocol.json"
REPOS={"youtube-dl":ROOT/"experiments/bench-source/youtube-dl",
       "tqdm":ROOT/"experiments/bench-source/tqdm"}
MAX_ARCHIVE_BYTES=22_000_000
IMAGE_TAG="nykra-py38-pytest:v20nose"

def manifest():
    raw=PROTOCOL.read_bytes()
    p=json.loads(raw)
    if p["id"]!="nykra-unseen-cross-project-replication-v1":
        raise ValueError("unrecognized study")
    if hashlib.sha256(Path(__file__).with_name("v20_hidden_spec.py").read_bytes()).hexdigest()!=p["hidden_source_sha256"]:
        raise ValueError("withheld verifier changed")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}",p["docker_image_id"]):
        raise ValueError("unverified Docker image ID")
    if not {t["project"] for t in p["tasks"]}.issubset(set(REPOS)):
        raise ValueError("unregistered project")
    return p,hashlib.sha256(raw).hexdigest()

def _git(task,commit,filename):
    if not re.fullmatch(r"[a-f0-9]{40}",commit):
        raise ValueError("invalid sha1 Git commit")
    if filename not in (task["source_file"],task["test_file"]):
        raise ValueError("unregistered upstream path")
    run=subprocess.run(["git","show",commit+":"+filename],cwd=REPOS[task["project"]],
                       capture_output=True,timeout=40)
    if run.returncode:
        raise RuntimeError("pinned upstream blob unavailable")
    return run.stdout

def function_at(task, commit):
    return extract_function(_git(task,commit,task["source_file"]).decode("utf-8"),task["function"])

def export(task,folder:Path):
    commit=task["buggy_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}",commit):
        raise ValueError("invalid commit")
    proc=subprocess.run(["git","archive","--format=tar",commit],
                        cwd=REPOS[task["project"]],capture_output=True,timeout=90)
    if proc.returncode or len(proc.stdout)>MAX_ARCHIVE_BYTES:
        raise RuntimeError("source Git archive failed or exceeds limit")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout),mode="r:") as archive:
        total=0
        for member in archive:
            rel=Path(member.name.replace("\\","/"))
            if rel.is_absolute() or ".." in rel.parts or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe source archive member")
            target=folder/rel
            if member.isdir():
                target.mkdir(parents=True,exist_ok=True)
            else:
                total+=member.size
                if total>MAX_ARCHIVE_BYTES:
                    raise ValueError("source archive exceeds limit")
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as src,target.open("wb") as dst:
                    shutil.copyfileobj(src,dst)

def prepare(task,folder:Path,*,replacement=None):
    export(task,folder)
    test_path=folder/task["test_file"]
    test_path.parent.mkdir(parents=True,exist_ok=True)
    test_path.write_bytes(_git(task,task["fixed_commit"],task["test_file"]))
    (folder/"_nykra_v20_private_checks.py").write_text(HIDDEN_TEST_MODULES[task["id"]],
                                                       encoding="utf-8")
    if replacement is not None:
        file=folder/task["source_file"]
        file.write_text(replace_function(file.read_text(encoding="utf-8"),
                                         task["function"],replacement),
                        encoding="utf-8")
    (folder/"Dockerfile.nykra").write_text(
        "FROM "+IMAGE_TAG+"\nCOPY . /repo/\nWORKDIR /repo\n"+
        "ENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\n"+
        "USER 65534:65534\n",encoding="utf-8")
    (folder/".dockerignore").write_text(
        ".git\n.env\n.env.*\n**/__pycache__\n**/*.pyc\n",encoding="utf-8")

def _commands(task,mode):
    if mode=="public":
        return [_runner(task,task["public_test"])]
    if mode!="hidden":raise ValueError("unknown grading mode")
    commands=[["-B","-m","unittest","-q","_nykra_v20_private_checks"]]
    commands.extend([_runner(task,x) for x in task["hidden_upstream_tests"]])
    return commands

def _runner(task,test):
    if task["project"]=="tqdm":
        return ["-B","-m","pytest","-q","-p","no:cacheprovider",test]
    return ["-B","-m","unittest","-q",test]

def grade(task,*,mode,candidate=None):
    doc,_=manifest()
    if candidate is not None and (not isinstance(candidate,str) or
                                   len(candidate.encode("utf-8"))>10000):
        return {"status":"invalid_patch","passed":False}
    label="nykra-v20-"+uuid.uuid4().hex[:15]
    built=False
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-v20-eval-") as tmp:
        root=Path(tmp)
        try:
            image_check=subprocess.run(["docker","image","inspect","--format","{{.Id}}",IMAGE_TAG],
                                       capture_output=True,timeout=15)
            if (image_check.returncode or
                image_check.stdout.decode(errors="replace").strip()!=doc["docker_image_id"]):
                return {"status":"base_image_mismatch","passed":False}
            prepare(task,root,replacement=candidate)
            build=subprocess.run(["docker","build","--pull=false","--network","none",
                                   "-f",str(root/"Dockerfile.nykra"),"-t",label,str(root)],
                                  capture_output=True,timeout=90)
            if build.returncode:
                return {"status":"build_error","passed":False,
                        "build_stderr_sha256":hashlib.sha256(build.stderr).hexdigest()}
            built=True
            insp=subprocess.run(["docker","image","inspect","--format","{{.Id}}",label],
                                capture_output=True,timeout=15)
            image=insp.stdout.decode(errors="replace").strip()
            if insp.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64}",image):
                return {"status":"image_inspect_error","passed":False}
            records=[]
            for command in _commands(task,mode):
                argv=["docker","run","--rm","--pull","never","--network","none",
                      "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                      "--pids-limit","64","--memory","384m","--memory-swap","384m",
                      "--cpus","1","--user","65534:65534",
                      "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=48m",
                      "--workdir","/repo","--env","PYTHONPATH=/repo",
                      "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1",
                      "--entrypoint","python",image,*command]
                try:
                    run=subprocess.run(argv,capture_output=True,timeout=45)
                    result="ok" if run.returncode==0 else "test_failed"
                    records.append({"status":result,"exit_code":run.returncode,
                        "stderr_sha256":hashlib.sha256(run.stderr).hexdigest(),
                        "stdout_sha256":hashlib.sha256(run.stdout).hexdigest(),
                        "stderr_preview":run.stderr.decode("utf-8",errors="replace")[-900:]
                        if mode=="preflight" else None})
                except subprocess.TimeoutExpired:
                    records.append({"status":"timeout"})
                    break
            status=("ok" if len(records)==len(_commands(task,mode)) and
                    all(x["status"]=="ok" for x in records) else
                    "timeout" if any(x["status"]=="timeout" for x in records)
                    else "test_failed")
            return {"status":status,"passed":status=="ok",
                    "checks":records,"mode":mode,
                    "elapsed_seconds":round(time.monotonic()-started,2)}
        except (OSError,RuntimeError,ValueError,KeyError,UnicodeError,
                SyntaxError,subprocess.TimeoutExpired) as err:
            return {"status":"setup_error","passed":False,
                    "error_type":type(err).__name__}
        finally:
            if built:
                try:subprocess.run(["docker","image","rm","-f",label],
                                   capture_output=True,timeout=20)
                except (OSError,subprocess.TimeoutExpired):pass

def prevalidate(task):
    gold=function_at(task,task["fixed_commit"])
    results={"public_buggy":grade(task,mode="public"),
             "public_reference":grade(task,mode="public",candidate=gold),
             "hidden_buggy":grade(task,mode="hidden"),
             "hidden_reference":grade(task,mode="hidden",candidate=gold)}
    statuses={k:v["status"] for k,v in results.items()}
    results["eligible"]=(statuses=={
        "public_buggy":"test_failed","public_reference":"ok",
        "hidden_buggy":"test_failed","hidden_reference":"ok"})
    return results
