"""Opt-in diagnostic grading of HISTORICAL v20 public tests only.

Runs the exact registered upstream public test in offline digest-pinned Docker;
does not expose hidden test data or execute model-authored code on the host.
"""
from __future__ import annotations
import hashlib,subprocess,tempfile,time,uuid
from pathlib import Path
from .v20_grader import manifest,prepare,IMAGE_TAG,_runner
from .repair_feedback import safe_feedback,validate_replacement
from .v20_grader import function_at

def grade_public_detailed(task,candidate):
    m,_=manifest()
    if not any(t["id"]==task["id"] for t in m["tasks"]):
        raise ValueError("historical task is not allowlisted")
    bug=function_at(task,task["buggy_commit"])
    issue=validate_replacement(candidate,name=task["function"],original=bug)
    if issue is not None:return issue
    tag="nykra-public-detail-"+uuid.uuid4().hex[:13]
    now=time.monotonic()
    built=False
    with tempfile.TemporaryDirectory(prefix="nykra-public-feedback-") as temp:
        try:
            root=Path(temp)
            check=subprocess.run(["docker","image","inspect","--format","{{.Id}}",IMAGE_TAG],
                                 capture_output=True,timeout=15)
            if check.returncode or check.stdout.decode().strip()!=m["docker_image_id"]:
                return {"status":"evaluator_image_mismatch","passed":False}
            prepare(task,root,replacement=candidate)
            imagefile=root/"Dockerfile.nykra"
            build=subprocess.run(["docker","build","--pull=false","--network","none",
                                  "-f",str(imagefile),"-t",tag,str(root)],
                                  capture_output=True,timeout=90)
            if build.returncode:
                return {"status":"evaluator_build_error","passed":False}
            built=True
            inspect=subprocess.run(["docker","image","inspect","--format","{{.Id}}",tag],
                                   capture_output=True,timeout=15)
            image=inspect.stdout.decode().strip()
            if inspect.returncode or not image.startswith("sha256:"):
                return {"status":"evaluator_image_inspect_error","passed":False}
            argv=["docker","run","--rm","--pull","never","--network","none",
                  "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                  "--pids-limit","64","--memory","384m","--memory-swap","384m",
                  "--cpus","1","--user","65534:65534",
                  "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=48m",
                  "--workdir","/repo","--env","PYTHONPATH=/repo",
                  "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1",
                  "--entrypoint","python",image,*_runner(task,task["public_test"])]
            proc=subprocess.run(argv,capture_output=True,timeout=45)
            status="ok" if proc.returncode==0 else (
                "evaluator_runtime_error" if proc.returncode in (125,126,127)
                else "test_failed")
            result={"status":status,"passed":status=="ok",
                    "exit_code":proc.returncode,
                    "stdout_sha256":hashlib.sha256(proc.stdout).hexdigest(),
                    "stderr_sha256":hashlib.sha256(proc.stderr).hexdigest(),
                    "elapsed_seconds":round(time.monotonic()-now,3)}
            if status=="test_failed":
                result["diagnostic"]=safe_feedback(proc.stderr.decode("utf-8","replace"))
            return result
        except (OSError,ValueError,subprocess.TimeoutExpired,RuntimeError) as exc:
            return {"status":"evaluator_exception","passed":False,
                    "error_class":type(exc).__name__}
        finally:
            if built:
                try:subprocess.run(["docker","image","rm","-f",tag],
                                   capture_output=True,timeout=20)
                except (OSError,subprocess.TimeoutExpired):pass
