"""Portable immutable v0.23 real Git/Docker replay provenance for every session."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import agent_workflow as wf
from .v20_grader import EVIDENCE, ROOT
from .v23_replay import frozen


def export():
    _, proto_sha=frozen()
    index=EVIDENCE/"v23_session_export_index.json"
    if index.exists():
        raise ValueError("will not overwrite portable evidence")
    doc={"schema":"nykra-v23-portable-replay-sessions-v1",
         "protocol_sha256":proto_sha,
         "source":"Previously model-generated source replayed with NO new model calls",
         "sessions":[]}
    unique=set()
    for issue in (27,43):
        record=json.loads((EVIDENCE/f"v23_reuse_youtube_dl_{issue}.json").read_bytes())
        if record["protocol_sha256"]!=proto_sha or record["status"]!="completed":
            raise ValueError("unverified trial")
        for mode in ("ordinary","shared"):
            for arm in ("depth","adaptive"):
                sid=record["conditions"][mode]["outcomes"][arm]["session_id"]
                if sid in unique:
                    raise ValueError("duplicate host session")
                unique.add(sid)
                origin=wf._folder(sid)
                if origin.is_symlink() or (origin/"OWNER").read_text(encoding="ascii")!=wf._OWNER:
                    raise ValueError("invalid session source ownership")
                raw=(origin/"state.json").read_bytes()
                state=json.loads(raw)
                if state["status"]!="finished" or state["id"]!=sid or state["task_id"]!=f"youtube-dl-{issue}":
                    raise ValueError("session task/outcome mismatch")
                names=["state.json"]+[x["id"]+".diff" for x in state["attempts"]
                                       if x["patch_sha256"] is not None]
                folder=EVIDENCE/"v23_sessions"/sid
                if folder.exists():
                    raise ValueError("evidence already exported")
                folder.mkdir(parents=True,exist_ok=False)
                files=[]
                for name in names:
                    path=origin/name
                    if not path.is_file() or path.is_symlink() or path.stat().st_size>90000:
                        raise ValueError("invalid model-source-bearing artifact")
                    blob=path.read_bytes()
                    dest=folder/name
                    with dest.open("xb") as out:
                        out.write(blob)
                    files.append({"path":dest.relative_to(ROOT).as_posix(),
                                  "bytes":len(blob),
                                  "sha256":hashlib.sha256(blob).hexdigest()})
                doc["sessions"].append({"session_id":sid,"task_id":state["task_id"],
                                        "mode":mode,"arm":arm,"files":files})
    if len(doc["sessions"])!=8:
        raise ValueError("not all conditions exported")
    doc["session_count"]=len(doc["sessions"])
    doc["file_count"]=sum(len(x["files"]) for x in doc["sessions"])
    index.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")
    return index
