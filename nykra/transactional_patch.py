"""Fail-closed, multi-file Git patch trial and optional atomic workspace promotion.

Patch proposals are evaluated in a disposable Git checkout. The user's
working tree is not changed if the patch/test fails. Explicitly approved
promotion is guarded by a per-repo lock and exact clean-HEAD preconditions,
with rollback of the affected files if Git apply fails or verification fails.

This is NOT a security sandbox for malicious code. Prefer the restricted,
pinned Docker test executor for untrusted proposals. Trusted local test
execution requires a separate explicit opt-in.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath

from .workstation import _single_instance

MAX_PATCH_BYTES = 128 * 1024
MAX_FILES = 16
MAX_FILE_BYTES = 2 * 1024 * 1024
_HEADER = re.compile(r"^diff --git a/([A-Za-z0-9._/-]+) b/([A-Za-z0-9._/-]+)$")
_VALID_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
_RESERVED = {"con", "prn", "aux", "nul", *{f"com{i}" for i in range(1, 10)},
             *{f"lpt{i}" for i in range(1, 10)}}
_BAD_METADATA = ("rename from ", "rename to ", "copy from ", "copy to ",
                 "old mode ", "new mode ", "GIT binary patch", "Binary files ",
                 "similarity index ", "dissimilarity index ")


class PatchRejected(ValueError):
    """The proposed patch violates the strict transactional subset."""


def _run(argv, *, cwd=None, timeout=30):
    try:
        return subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PatchRejected("Git operation unavailable or timed out") from exc


def _git(root, *args, timeout=30):
    return _run(["git", "-C", str(root), *args], timeout=timeout)


def _digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _path(name: str):
    if not isinstance(name, str) or not _VALID_PATH.fullmatch(name):
        raise PatchRejected("unsupported file path syntax")
    components = name.split("/")
    if not components or any(
            p in ("", ".", "..") or p.endswith((" ", ".")) or p.lower().split(".")[0] in _RESERVED
            for p in components):
        raise PatchRejected("unsafe path component")
    if ".git" in [part.lower() for part in components]:
        raise PatchRejected("Git internals may not be patched")
    if name.startswith("/") or "//" in name:
        raise PatchRejected("absolute or ambiguous file path")
    return name


def _safe_file(root: Path, name: str, *, allow_absent=True):
    _path(name)
    current=root
    bits=name.split("/")
    for i, bit in enumerate(bits):
        current=current/bit
        if current.is_symlink():
            raise PatchRejected("path traverses a symbolic link")
        if current.exists():
            if i<len(bits)-1 and not current.is_dir():
                raise PatchRejected("parent is not a directory")
            if i==len(bits)-1 and not current.is_file():
                raise PatchRejected("patch target is not a regular file")
        elif not allow_absent and i==len(bits)-1:
            raise PatchRejected("original patch target missing")
    if current.is_file() and current.stat().st_size>MAX_FILE_BYTES:
        raise PatchRejected("file exceeds allowed size")
    return current


def parse_patch(patch: str, allowed_paths):
    """Only straightforward textual modifications, additions and deletions."""
    if not isinstance(patch, str) or not 0<len(patch.encode("utf-8"))<=MAX_PATCH_BYTES:
        raise PatchRejected("patch is empty or too large")
    if "\x00" in patch or "\r" in patch:
        raise PatchRejected("binary or CRLF patch is unsupported")
    if not patch.endswith("\n"):
        raise PatchRejected("patch must terminate with newline")
    if isinstance(allowed_paths, str):
        raise PatchRejected("allowed_paths must be a sequence of exact paths")
    allow=set(map(_path,allowed_paths))
    if not allow or len(allow)>MAX_FILES:
        raise PatchRejected("explicit bounded path allowlist required")
    lines=patch.splitlines(keepends=True)
    starts=[i for i,line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts or starts[0]!=0 or len(starts)>MAX_FILES:
        raise PatchRejected("patch requires 1-16 Git diff sections")
    records=[]
    folded=set()
    for i, begin in enumerate(starts):
        chunk=lines[begin:starts[i+1] if i+1<len(starts) else len(lines)]
        match=_HEADER.fullmatch(chunk[0].rstrip("\n"))
        if not match or match.group(1)!=match.group(2):
            raise PatchRejected("renames or quoted/unsafe paths are not supported")
        name=_path(match.group(1))
        if name not in allow or name.casefold() in folded:
            raise PatchRejected("duplicate or non-allowlisted file")
        folded.add(name.casefold())
        if any(line.startswith(_BAD_METADATA) for line in chunk):
            raise PatchRejected("binary, rename, copy or mode changes are forbidden")
        modes=[line.rstrip("\n") for line in chunk if line.startswith(("new file mode ", "deleted file mode "))]
        if any(line not in ("new file mode 100644","deleted file mode 100644") for line in modes):
            raise PatchRejected("only regular file permissions 100644 are permitted")
        headers=[line.rstrip("\n") for line in chunk if line.startswith(("--- ", "+++ "))]
        if len(headers)!=2 or not any(line.startswith("@@ ") for line in chunk):
            raise PatchRejected("patch requires exactly two file headers and a hunk")
        old,new=headers
        if old not in (f"--- a/{name}", "--- /dev/null") or new not in (
                f"+++ b/{name}", "+++ /dev/null"):
            raise PatchRejected("file headers do not match Git section")
        if old=="--- /dev/null" and new=="+++ /dev/null":
            raise PatchRejected("file may not both be added and deleted")
        op="add" if old=="--- /dev/null" else "delete" if new=="+++ /dev/null" else "modify"
        if op=="add" and "new file mode 100644" not in modes:
            raise PatchRejected("new file requires ordinary file mode")
        if op=="delete" and "deleted file mode 100644" not in modes:
            raise PatchRejected("deleted file requires ordinary file mode")
        records.append({"path":name,"operation":op})
    return records


def _repository(root):
    root=Path(root).resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise PatchRejected("repository must be a real directory")
    top=_git(root,"rev-parse","--show-toplevel")
    if top.returncode:
        raise PatchRejected("not a Git worktree")
    if Path(os.fsdecode(top.stdout).strip()).resolve()!=root:
        raise PatchRejected("root must be exact Git checkout top level")
    head=_git(root,"rev-parse","--verify","HEAD")
    if head.returncode:
        raise PatchRejected("repo requires an existing commit")
    if _git(root,"status","--porcelain=v1","--untracked-files=all").stdout.strip():
        raise PatchRejected("repository must be clean, including untracked files")
    return root, head.stdout.decode("ascii").strip()


def _preflight(root, records):
    for row in records:
        target=_safe_file(root,row["path"],allow_absent=row["operation"]=="add")
        if row["operation"]=="add" and target.exists():
            raise PatchRejected("added path already exists")
        if row["operation"]!="add" and not target.is_file():
            raise PatchRejected("modify/delete target absent or nonregular")


def _check_git(root,patch_file):
    check=_git(root,"apply","--check","--whitespace=error",str(patch_file),timeout=45)
    if check.returncode:
        raise PatchRejected("Git refused proposed patch")
    result=_git(root,"apply","--whitespace=error",str(patch_file),timeout=45)
    if result.returncode:
        raise PatchRejected("Git failed applying patch")


def _trial(root,head,patch,records,tempdir):
    """Clone only the committed tree; never copy host secrets/untracked data."""
    checkout=Path(tempdir)/"checkout"
    clone=_run(["git","clone","--quiet","--local","--no-hardlinks","--no-checkout",
                "--",str(root),str(checkout)],timeout=90)
    if clone.returncode:
        raise PatchRejected("unable to construct disposable local checkout")
    if _git(checkout,"checkout","--quiet","--detach",head,timeout=60).returncode:
        raise PatchRejected("unable to checkout pinned revision")
    _preflight(checkout,records)
    patch_file=Path(tempdir)/"approved.diff"
    patch_file.write_bytes(patch.encode("utf-8"))
    _check_git(checkout,patch_file)
    for row in records:
        dest=_safe_file(checkout,row["path"])
        if row["operation"]=="delete" and dest.exists():
            raise PatchRejected("deleted file still present in checkout")
        if row["operation"]!="delete" and not dest.is_file():
            raise PatchRejected("expected changed regular file missing")
        if dest.is_file() and dest.stat().st_size>MAX_FILE_BYTES:
            raise PatchRejected("patched file exceeds size limit")
    changes={}
    for row in records:
        name=row["path"]
        dest=checkout/name
        changes[name]={"operation":row["operation"],
                       "before_sha256":_digest((root/name).read_bytes()) if (root/name).is_file() else None,
                       "after_sha256":_digest(dest.read_bytes()) if dest.is_file() else None}
    return checkout,patch_file,changes


def _run_docker(checkout,test_args,image_id,timeout):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",str(image_id)):
        raise PatchRejected("pinned Docker image SHA-256 is required")
    if tuple(test_args[:3])!=("-B","-m","unittest"):
        raise PatchRejected("Docker test must invoke Python unittest without shell")
    if any(not isinstance(x,str) or len(x)>200 or not re.fullmatch(r"[A-Za-z0-9_./-]+",x)
           for x in test_args):
        raise PatchRejected("invalid Docker unittest argument")
    if _run(["docker","image","inspect","--format","{{.Id}}",image_id],timeout=20).returncode:
        raise PatchRejected("pinned Docker test image unavailable")
    # Always use the SHA, never a mutable tag.
    cmd=["docker","run","--rm","--pull","never","--network","none","--read-only",
         "--cap-drop","ALL","--security-opt","no-new-privileges",
         "--pids-limit","64","--memory","384m","--memory-swap","384m",
         "--cpus","1","--user","65534:65534","--tmpfs",
         "/tmp:rw,nosuid,nodev,noexec,size=32m",
         "--mount",f"type=bind,source={checkout},target=/repo,readonly",
         "--workdir","/repo","--env","PYTHONDONTWRITEBYTECODE=1",
         "--entrypoint","python",image_id,*test_args]
    return _run(cmd,timeout=timeout)


def _backup(root,records):
    return {x["path"]: ((root/x["path"]).read_bytes(),(root/x["path"]).stat().st_mode)
            if (root/x["path"]).is_file() else None for x in records}


def _restore(root,snapshot):
    for rel,state in snapshot.items():
        target=root/rel
        if state is None:
            target.unlink(missing_ok=True)
        else:
            content,mode=state
            target.parent.mkdir(parents=True,exist_ok=True)
            # Content restores even if Git had applied only one of many files.
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as temp:
                tmp=Path(temp.name)
                temp.write(content)
            try:
                os.chmod(tmp,stat.S_IMODE(mode))
                os.replace(tmp,target)
            finally:
                tmp.unlink(missing_ok=True)


def run_transaction(root,patch,*,allowed_paths,test_args=("-B","-m","unittest",
                    "discover","-s","tests"),executor="docker",docker_image_id=None,
                    allow_trusted_local_tests=False,promote=False,approve=False,
                    timeout=90):
    """Validate, execute tests in isolated committed clone, promote if approved.

    Never commits/pushes. A failing patch or failing test leaves the original
    Git worktree untouched. Promotion is fail-closed and rollback-aware.
    """
    if approve is not True:
        raise PatchRejected("explicit approval required")
    if type(promote) is not bool or type(allow_trusted_local_tests) is not bool:
        raise PatchRejected("invalid safety flags")
    if executor not in ("docker","local"):
        raise PatchRejected("unknown test executor")
    if executor=="local" and not allow_trusted_local_tests:
        raise PatchRejected("unsafe local code execution requires separate explicit trust")
    if type(timeout) not in (int,float) or not 1<=timeout<=300:
        raise PatchRejected("test timeout outside supported range")
    if not isinstance(test_args,(tuple,list)) or not test_args:
        raise PatchRejected("tests require an explicit argument list")
    root,head=_repository(root)
    records=parse_patch(patch,allowed_paths)
    _preflight(root,records)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nykra-transaction-") as tmp:
        checkout,proposal_file,changes=_trial(root,head,patch,records,tmp)
        if executor=="docker":
            test=_run_docker(checkout,test_args,docker_image_id,timeout)
        else:
            if not all(isinstance(x,str) for x in test_args):
                raise PatchRejected("invalid trusted test arguments")
            test=_run([os.sys.executable,*test_args],cwd=checkout,timeout=timeout)
        evidence={"schema":"nykra-multifile-transaction-v1",
                  "upstream_head":head,"patch_sha256":_digest(patch.encode("utf-8")),
                  "files":changes,"file_count":len(changes),
                  "executor":executor,"test_args":list(test_args),
                  "test_exit_code":test.returncode,
                  "test_stdout_sha256":_digest(test.stdout),
                  "test_stderr_sha256":_digest(test.stderr),
                  "test_stdout_preview":test.stdout.decode("utf-8","replace")[-1200:],
                  "test_stderr_preview":test.stderr.decode("utf-8","replace")[-1200:],
                  "tests_passed":test.returncode==0,
                  "promoted":False}
        if not evidence["tests_passed"] or not promote:
            evidence["elapsed_seconds"]=round(time.monotonic()-started,3)
            return evidence
        gitdir=_git(root,"rev-parse","--absolute-git-dir")
        if gitdir.returncode:
            raise PatchRejected("unable to locate Git directory for lock")
        gitpath=Path(os.fsdecode(gitdir.stdout).strip()).resolve()
        with _single_instance(gitpath/"nykra-transaction.lock"):
            root2,head2=_repository(root)
            if head2!=head or root2!=root:
                raise PatchRejected("repository changed during test evaluation")
            _preflight(root,records)
            snapshot=_backup(root,records)
            # The tested checkout may normalize line endings differently from
            # the original Windows worktree. Do not apply the unified diff
            # again: promote exactly the already-tested checkout bytes. All
            # original paths were revalidated under the transaction lock.
            try:
                for name,proof in changes.items():
                    target=_safe_file(root,name)
                    before=(target.read_bytes() if target.is_file() else None)
                    if proof["before_sha256"] != (
                            _digest(before) if before is not None else None):
                        raise PatchRejected("repository file changed since test started")
                    after_path=checkout/name
                    content=after_path.read_bytes() if after_path.is_file() else None
                    if proof["after_sha256"] != (
                            _digest(content) if content is not None else None):
                        raise PatchRejected("tested checkout source changed unexpectedly")
                    if content is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as out:
                            temp_target=Path(out.name)
                            out.write(content)
                            out.flush()
                            os.fsync(out.fileno())
                        try:
                            os.chmod(temp_target,stat.S_IMODE(snapshot[name][1]) if snapshot[name] else 0o644)
                            os.replace(temp_target,target)
                        finally:
                            temp_target.unlink(missing_ok=True)
                    if proof["after_sha256"] != (
                            _digest(target.read_bytes()) if target.is_file() else None):
                        raise PatchRejected("promoted file does not match tested checkout")
            except BaseException:
                _restore(root,snapshot)
                raise
            evidence["promoted"]=True
        evidence["elapsed_seconds"]=round(time.monotonic()-started,3)
        return evidence
