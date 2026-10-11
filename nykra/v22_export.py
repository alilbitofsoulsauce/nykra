"""Portable, immutable export of approved v0.22 workflow patch provenance.

The original live sessions remain owned by the local execution host.
Export only the explicitly registered paired runs and the CLI reference
control, not arbitrary session directories or host data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agent_workflow import SESSIONS, _OWNER
from .v20_grader import EVIDENCE, ROOT
from .v22_paired import frozen

def sha(blob: bytes):
    return hashlib.sha256(blob).hexdigest()

def export():
    p, phash = frozen()
    index = EVIDENCE / "v22_session_export_index.json"
    if index.exists():
        raise ValueError("will not overwrite portable session evidence")
    pairs = []
    sids = []
    for name in ("youtube-dl-27", "youtube-dl-43"):
        raw = json.loads((EVIDENCE / ("v22_workflow_pair_" + name.replace("-","_") + ".json")).read_text())
        if raw["protocol_sha256"] != phash:
            raise ValueError("pair does not match locked protocol")
        for result in raw["results"].values():
            sids.append(result["session_id"])
    reference = json.loads((EVIDENCE / "v22_cli_reference_smoke.json").read_text())
    if reference["candidate_origin"] != "UPSTREAM_REFERENCE_CONTROL_NOT_MODEL_GENERATED":
        raise ValueError("untrusted control attribution")
    sids.append(reference["session_id"])
    if len(set(sids))!=5:
        raise ValueError("expected four model sessions and one reference control")
    for sid in sids:
        if len(sid)!=32 or any(c not in "0123456789abcdef" for c in sid):
            raise ValueError("invalid session id")
        origin = SESSIONS / sid
        if origin.is_symlink() or (origin / "OWNER").read_text(encoding="ascii") != _OWNER:
            raise ValueError("untrusted session owner")
        target = EVIDENCE / "v22_sessions" / sid
        if target.exists():
            raise ValueError("will not overwrite exported session")
        target.mkdir(parents=True)
        raw = (origin / "state.json").read_bytes()
        state = json.loads(raw)
        if state["id"] != sid or state["status"]!="finished":
            raise ValueError("incomplete session")
        files = ["state.json"] + [x["id"]+".diff" for x in state["attempts"]
                                  if x["patch_sha256"] is not None]
        copied = []
        for name in files:
            src = origin / name
            if src.is_symlink() or not src.is_file() or src.stat().st_size > 80000:
                raise ValueError("unsafe or overlarge export file")
            content = src.read_bytes()
            out = target / name
            with out.open("xb") as file:
                file.write(content)
            if out.read_bytes() != content:
                raise ValueError("session export byte mismatch")
            copied.append({"path":out.relative_to(ROOT).as_posix(),
                           "sha256":sha(content),"bytes":len(content)})
        pairs.append({"session_id":sid,"role":("reference_control" if sid==reference["session_id"]
                                              else "codex_model_trial"),
                      "files":copied})
    doc = {"schema":"nykra-v22-session-portable-evidence-export-v1",
           "v22_protocol_sha256":phash,
           "session_count":len(pairs),
           "model_trial_sessions":4,
           "reference_control_sessions":1,
           "files":pairs,
           "contains_public_upstream_model_authored_code":True,
           "does_not_contain_agent_credentials":True,
           "no_effectiveness_claim":True}
    index.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")
    return index
