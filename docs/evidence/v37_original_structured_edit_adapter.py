"""Strict provider-neutral exact source edits to Git patch construction.

Model returns JSON exact source span replacements. Only registered paths.
Adapter calculates hunk counts in Python, without executing candidate code or
mutating any checked-out source.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import PurePosixPath
from .transactional_patch import PatchRejected, parse_patch, MAX_PATCH_BYTES

MAX_EDITS=12
MAX_TEXT_BYTES=5000
MAX_SOURCE_BYTES=2_000_000


def exact_edits_to_diff(response, *, originals, allowed_paths):
    """Generate a Git patch from exact non-overlapping original text spans."""
    if not isinstance(response,str) or len(response.encode("utf-8"))>60000:
        raise PatchRejected("structured edit response outside size bound")
    try:
        data=json.loads(response.strip())
    except (ValueError,TypeError) as exc:
        raise PatchRejected("structured edits require valid JSON") from exc
    if type(data) is not dict or set(data)!={"edits"}:
        raise PatchRejected("expected object containing edits only")
    edits=data["edits"]
    if not isinstance(edits,list) or not 1<=len(edits)<=MAX_EDITS:
        raise PatchRejected("requires 1-12 bounded edits")
    if not isinstance(originals,dict) or not isinstance(allowed_paths,(list,tuple)):
        raise PatchRejected("registered originals and allowlist required")
    allow=set(allowed_paths)
    if len(allow)!=len(allowed_paths) or not allow or set(originals)!=allow:
        raise PatchRejected("source identity and exact allowed paths mismatch")
    contents={}
    for name,value in originals.items():
        if (not isinstance(name,str) or str(PurePosixPath(name))!=name or
                not isinstance(value,bytes) or len(value)>MAX_SOURCE_BYTES):
            raise PatchRejected("bad original source identity or size")
        try:decoded=value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PatchRejected("original source is not UTF-8") from exc
        if "\r" in decoded or "\x00" in decoded or not decoded.endswith("\n"):
            raise PatchRejected("original source must have clean LF newline")
        contents[name]=decoded
    locations={name:[] for name in allow}
    provenance=[]
    for i,item in enumerate(edits):
        if type(item) is not dict or set(item)!={"path","old","new"}:
            raise PatchRejected("each edit must contain path, old and new")
        name=item["path"]
        if not isinstance(name,str) or name not in allow:
            raise PatchRejected("path outside exact allowlist")
        old=item["old"];new=item["new"]
        if (not isinstance(old,str) or not old or len(old.encode())>MAX_TEXT_BYTES
                or "\r" in old or "\x00" in old or
                not isinstance(new,str) or len(new.encode())>MAX_TEXT_BYTES
                or "\r" in new or "\x00" in new or old==new):
            raise PatchRejected("invalid or no-op source edit")
        original=contents[name]
        if original.count(old)!=1:
            raise PatchRejected("old span not unique in pinned original")
        start=original.index(old);end=start+len(old)
        if any(start<b and a<end for a,b,_ in locations[name]):
            raise PatchRejected("overlapping original-source edit spans")
        locations[name].append((start,end,new))
        provenance.append({"edit":i+1,"path":name,"start":start,
                           "old_bytes":len(old.encode()),"new_bytes":len(new.encode())})
    modified={}
    for name in sorted(allow):
        if not locations[name]:continue
        source=contents[name];target=source
        for start,end,new in sorted(locations[name],reverse=True):
            target=target[:start]+new+target[end:]
        if target==source or len(target.encode())>MAX_SOURCE_BYTES or not target.endswith("\n"):
            raise PatchRejected("generated source invalid or unchanged")
        modified[name]=target
    sections=[]
    for name,new in sorted(modified.items()):
        lines=list(difflib.unified_diff(
            contents[name].splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/"+name,tofile="b/"+name,
            n=3,lineterm="\n"))
        if not lines or any(not line.endswith("\n") for line in lines):
            raise PatchRejected("generated diff cannot preserve newline")
        sections.append("diff --git a/"+name+" b/"+name+"\n"+"".join(lines))
    patch="".join(sections)
    if len(patch.encode("utf-8"))>MAX_PATCH_BYTES:
        raise PatchRejected("generated patch exceeds size bound")
    parsed=parse_patch(patch,allowed_paths)
    if {x["path"] for x in parsed}!=set(modified):
        raise PatchRejected("generated patch path mismatch")
    return patch,{"schema":"nykra-exact-edit-adapter-v1","edits":provenance,
                  "files_changed":sorted(modified),
                  "patch_sha256":hashlib.sha256(patch.encode()).hexdigest()}
