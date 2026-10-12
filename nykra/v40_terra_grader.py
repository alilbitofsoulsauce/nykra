"""Frozen historical two-production-file Git-diff grader (BugsInPy PySnooper #1).

Never executes model-authored source on the Windows workstation. Builds upstream
buggy Git source from a pinned commit, applies only allowlisted patch paths, and
runs original upstream public tests / separately pre-frozen hidden tests inside
a restricted networkless Docker image verified by immutable ID.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from . import v20_grader as upstream
from .repair_feedback import safe_feedback
from .transactional_patch import PatchRejected, parse_patch

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/evidence/v40_terra_policy_protocol.json"
PROTOCOL_SHA="be63c8920d383660fb2fc76f1637661dbf77edaa4974a84ace863132b5e7978e"
DANGER={"base_image_mismatch","build_error","image_inspect_error","setup_error",
        "evaluator_timeout","evaluator_runtime_error"}


upstream.REPOS.setdefault("PySnooper", ROOT/"experiments/bench-source/pysnooper")


def load_protocol(task_id="PySnooper-1"):
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA:
        raise ValueError("v40 frozen protocol SHA changed")
    if task_id!="PySnooper-1":
        raise ValueError("task is not registered")
    p=json.loads(raw)
    if p["project"]!="PySnooper" or p["issue"]!=task_id:
        raise ValueError("source or issue identity mismatch")
    if p["allowed_production_paths"]!=["pysnooper/pycompat.py","pysnooper/tracer.py"]:
        raise ValueError("invalid source allowlist")
    for stem in ("public","hidden"):
        path=ROOT/p[stem+"_source_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=p[stem+"_source_sha256"]:
            raise ValueError("frozen "+stem+" test SHA changed")
    standard,_=upstream.manifest()
    if standard["docker_image_id"]!=p["pinned_image_id"]:
        raise ValueError("pinned Docker image mismatch")
    return p



def git_blob(commit,path,task_id):
    p=load_protocol(task_id)
    if commit not in (p["buggy_commit"],p["fixed_commit"]):
        raise ValueError("unregistered revision")
    if path not in p["allowed_production_paths"]:
        raise ValueError("unregistered Git path")
    work=upstream.REPOS["PySnooper"]
    result=subprocess.run(["git","show",commit+":"+path],cwd=work,
                          capture_output=True,timeout=30)
    if result.returncode:raise ValueError("upstream frozen source blob unavailable")
    return result.stdout


def source_task(task_id):
    p=load_protocol(task_id)
    return {"project":"PySnooper","buggy_commit":p["buggy_commit"]}


def apply_candidate(root,patch,paths):
    if not isinstance(patch,str):
        return {"status":"invalid_patch","passed":False,"diagnostic":"Expected UTF-8 Git diff"}
    if any(c=="\r" for c in patch):
        return {"status":"invalid_patch","passed":False,"diagnostic":"CRLF in patch unsupported"}
    try:
        changed=parse_patch(patch,paths)
    except PatchRejected as ex:
        return {"status":"invalid_patch","passed":False,
                "diagnostic":safe_feedback(str(ex))}
    payload=root/"_nykra_v40_patch.diff"
    payload.write_text(patch,encoding="utf-8",newline="\n")
    try:
        checked=subprocess.run(["git","apply","--check","--whitespace=error",str(payload)],
                               cwd=root,capture_output=True,timeout=20)
        if checked.returncode:
            return {"status":"invalid_patch","passed":False,
                    "diagnostic":safe_feedback(checked.stderr.decode("utf-8","replace"))}
        applied=subprocess.run(["git","apply","--whitespace=error",str(payload)],
                               cwd=root,capture_output=True,timeout=20)
        if applied.returncode:
            return {"status":"invalid_patch","passed":False,
                    "diagnostic":safe_feedback(applied.stderr.decode("utf-8","replace"))}
        return {"status":"applied","file_count":len(changed),
                "paths":[x["path"] for x in changed]}
    except (OSError,subprocess.TimeoutExpired):
        return {"status":"setup_error","passed":False}


def grade(*,task_id,mode,patch=None,revision="buggy",public_feedback=True):
    if mode not in ("public","hidden"):raise ValueError("invalid evaluation mode")
    if revision not in ("buggy","reference"):raise ValueError("invalid revision")
    if revision=="reference" and patch is not None:
        raise ValueError("reference and candidate patch are mutually exclusive")
    p=load_protocol(task_id)
    if patch is not None and (not isinstance(patch,str) or
                             len(patch.encode("utf-8"))>131072):
        return {"status":"invalid_patch","passed":False}
    created=time.monotonic()
    docker_tag="nykra-v40-"+uuid.uuid4().hex[:13]
    built=False
    with tempfile.TemporaryDirectory(prefix="nykra-v40-docker-") as temp:
        root=Path(temp)
        try:
            image_check=subprocess.run(
                ["docker","image","inspect","--format","{{.Id}}",
                 p["pinned_image_tag"]],capture_output=True,timeout=15)
            if (image_check.returncode or image_check.stdout.decode("utf-8","replace").strip()
                    !=p["pinned_image_id"]):
                return {"status":"base_image_mismatch","passed":False}
            upstream.export(source_task(task_id),root)
            # Both test modules were authored and frozen before any provider call.
            for stem in ("public","hidden"):
                name=p[stem+"_suite"]+".py"
                (root/name).write_bytes((ROOT/p[stem+"_source_path"]).read_bytes())
            if revision=="reference":
                for name in p["allowed_production_paths"]:
                    (root/name).write_bytes(git_blob(p["fixed_commit"],name,task_id))
            elif patch is not None:
                checked=apply_candidate(root,patch,p["allowed_production_paths"])
                if checked["status"]!="applied":return checked
            dockerfile=root/"Dockerfile.nykra"
            dockerfile.write_text("FROM "+p["pinned_image_tag"]+
              "\nCOPY . /repo/\nWORKDIR /repo\nENV PYTHONPATH=/repo PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\nUSER 65534:65534\n",
              encoding="utf-8")
            (root/".dockerignore").write_text(
                ".git\n.env\n.env.*\n**/__pycache__\n**/*.pyc\n_nykra_v40_patch.diff\n",
                encoding="utf-8")
            build=subprocess.run(
                ["docker","build","--pull=false","--network","none",
                 "-t",docker_tag,"-f",str(dockerfile),str(root)],
                capture_output=True,timeout=90)
            if build.returncode:
                return {"status":"build_error","passed":False,
                        "build_stderr_sha256":hashlib.sha256(build.stderr).hexdigest()}
            built=True
            inspect=subprocess.run(["docker","image","inspect","--format","{{.Id}}",docker_tag],
                                   capture_output=True,timeout=15)
            sha=inspect.stdout.decode("ascii","replace").strip()
            if inspect.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64}",sha):
                return {"status":"image_inspect_error","passed":False}
            suite=(p["public_suite"] if mode=="public" else p["hidden_suite"])
            runner=["-B","-m","unittest","-q",suite]
            cmd=["docker","run","--rm","--pull","never","--network","none",
                 "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                 "--pids-limit","64","--memory","384m","--memory-swap","384m",
                 "--cpus","1","--user","65534:65534",
                 "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=48m",
                 "--workdir","/repo","--env","PYTHONPATH=/repo",
                 "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1",
                 "--entrypoint","python",sha,*runner]
            result=subprocess.run(cmd,capture_output=True,timeout=50)
            status=("ok" if result.returncode==0 else
                    "evaluator_runtime_error" if result.returncode in (125,126,127) else
                    "test_failed")
            receipt={"status":status,"passed":status=="ok","mode":mode,
                     "return_code":result.returncode,
                     "stdout_sha256":hashlib.sha256(result.stdout).hexdigest(),
                     "stderr_sha256":hashlib.sha256(result.stderr).hexdigest(),
                     "elapsed_seconds":round(time.monotonic()-created,2)}
            if mode=="public" and public_feedback and status=="test_failed":
                receipt["diagnostic"]=safe_feedback(result.stderr.decode("utf-8","replace"))
            return receipt
        except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
            return {"status":"setup_error","passed":False,
                    "error_type":type(exc).__name__}
        finally:
            if built:
                try:subprocess.run(["docker","image","rm","-f",docker_tag],
                                   capture_output=True,timeout=22)
                except (OSError,subprocess.TimeoutExpired):pass
