"""Portable frozen evidence for actual v0.24 cold/warm independent session checks."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from . import agent_workflow as wf
from .v20_grader import EVIDENCE, ROOT
from .v24_benchmark import frozen


def _sha(blob: bytes):
    return hashlib.sha256(blob).hexdigest()


def export():
    _, proto_sha = frozen()
    target=EVIDENCE/"v24_session_export_index.json"
    if target.exists():
        raise ValueError("will not overwrite v24 session index")
    sessions=[]
    seen=set()
    for number in (27,43):
        source=EVIDENCE/f"v24_cache_youtube_dl_{number}.json"
        record=json.loads(source.read_bytes())
        if record["status"]!="completed" or record["protocol_sha256"]!=proto_sha:
            raise ValueError("unverified cache benchmark")
        for mode in ("cold","cached"):
            for entry in record["conditions"][mode]["sessions"]:
                sid=entry["session_id"]
                if sid in seen:
                    raise ValueError("session already exported")
                seen.add(sid)
                folder=wf._folder(sid)
                if folder.is_symlink() or (folder/"OWNER").read_text(encoding="ascii")!=wf._OWNER:
                    raise ValueError("invalid live session owner")
                state_file=folder/"state.json"
                state=json.loads(state_file.read_bytes())
                if state["id"]!=sid or state["status"]!="finished" or len(state["attempts"])!=1:
                    raise ValueError("missing complete session")
                path=EVIDENCE/"v24_sessions"/sid
                if path.exists():
                    raise ValueError("refuse overwrite existing portable session")
                path.mkdir(parents=True)
                files=[]
                for filename in ("state.json","attempt-1.diff"):
                    original=folder/filename
                    if original.is_symlink() or not original.is_file() or original.stat().st_size>95000:
                        raise ValueError("unexpected session source")
                    blob=original.read_bytes()
                    dest=path/filename
                    with dest.open("xb") as out:
                        out.write(blob)
                    files.append({"path":dest.relative_to(ROOT).as_posix(),
                                  "sha256":_sha(blob),"bytes":len(blob)})
                sessions.append({"task":record["task_id"],"mode":mode,
                                 "session_id":sid,"policy":entry["policy"],
                                 "cache_hit":entry["public_cache_hit"],"files":files})
    if len(sessions)!=12:
        raise ValueError("expected 12 independent benchmark sessions")
    result={"schema":"nykra-v24-portable-real-cold-warm-sessions-v1",
            "protocol_sha256":proto_sha,"session_count":12,
            "new_model_calls":0,"source_model_outputs_reused_from_v22":True,
            "sessions":sessions}
    target.write_text(json.dumps(result,indent=2)+"\n")
    return target


def export_public_receipts():
    """Two genuine Docker-graded public receipts; never includes hidden results."""
    _, proto_sha=frozen()
    dest=EVIDENCE/"v24_public_receipt_index.json"
    if dest.exists():
        raise ValueError("will not overwrite public receipt index")
    items=[]
    for issue in ("youtube-dl-27","youtube-dl-43"):
        from pathlib import Path
        origin=ROOT/"experiments"/"v24-benchmark-cache"/issue
        candidates=list(origin.glob("*.json"))
        if len(candidates)!=1:
            raise ValueError("one unique receipt expected per issue")
        current=candidates[0]
        if current.is_symlink():
            raise ValueError("unsafe receipt")
        data=json.loads(current.read_bytes())
        if data["schema"]!="nykra-public-receipt-v24" or data["inputs"]["task_id"]!=issue:
            raise ValueError("receipt not from designated source")
        if data["inputs"]["protocol_sha256"]!=frozen()[0]["evaluator_sha256"]:
            raise ValueError("receipt evaluator mismatch")
        if "hidden" in data:
            raise ValueError("hidden verifier must not be cached")
        dest_dir=EVIDENCE/"v24_public_receipts"
        dest_dir.mkdir(exist_ok=True)
        out=dest_dir/current.name
        with out.open("xb") as f:
            content=current.read_bytes()
            f.write(content)
        items.append({"task_id":issue,"path":out.relative_to(ROOT).as_posix(),
                      "sha256":_sha(content),"bytes":len(content)})
    dest.write_text(json.dumps({"schema":"nykra-v24-public-cache-portable-index-v1",
                                "protocol_sha256":proto_sha,
                                "receipt_count":len(items),"receipts":items},indent=2)+"\n")
    return dest
