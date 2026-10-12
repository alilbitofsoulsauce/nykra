"""Reject accidental private files or obvious credentials in tracked OSS releases.

This is conservative hygiene, not a professional credential scanner.
Run after staging, and on CI for every commit.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parent.parent
REQUIRED={"LICENSE","README.md","pyproject.toml","CONTRIBUTING.md",
          "SECURITY.md","AGENTS.md","docs/MULTIFILE_TRANSACTION.md",
          "nykra/transactional_patch.py","tests/test_transactional_patch.py"}
FORBIDDEN_SEGMENTS={".venv","venv","node_modules","experiments",
                    "__pycache__", ".relai", ".git", "build","dist"}
SUSPICIOUS=[
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{25,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{36,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{24,}"),
    re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]


def _git_paths(*args):
    result=subprocess.run(["git","ls-files","-z",*args],cwd=ROOT,
                          capture_output=True,check=True)
    return {pathlib.PurePosixPath(x.decode("utf-8"))
            for x in result.stdout.split(b"\x00") if x}


def main(argv=None):
    parser=argparse.ArgumentParser(description="Audit files eligible for a public Nykra release")
    parser.add_argument("--include-untracked",action="store_true",
                        help="also scan non-ignored untracked release candidates before staging")
    args=parser.parse_args(argv)
    tracked=_git_paths("--cached")
    paths=tracked | (_git_paths("--others","--exclude-standard")
                     if args.include_untracked else set())
    names={p.as_posix() for p in tracked}
    errors=[]
    for needed in sorted(REQUIRED-names):
        errors.append(f"required OSS source not tracked: {needed}")
    for item in sorted(paths):
        path=ROOT/item
        suffix=item.suffix.lower()
        if set(x.lower() for x in item.parts)&FORBIDDEN_SEGMENTS:
            errors.append(f"prohibited release tree: {item}")
        if (item.name.startswith(".env") or suffix in (".pem",".key",".p12",".pfx",
                ".sqlite",".sqlite3",".db") or item.name in ("id_rsa","id_ed25519")):
            errors.append(f"potentially private file staged: {item}")
        if path.is_symlink() or not path.is_file():
            errors.append(f"tracked non-regular file: {item}")
            continue
        if path.stat().st_size>20*1024*1024:
            errors.append(f"unusually large tracked artifact: {item}")
            continue
        blob=path.read_bytes()
        for pattern in SUSPICIOUS:
            if pattern.search(blob):
                errors.append(f"possible credential, review manually: {item}")
                break
    if errors:
        for entry in errors:
            print("ERROR:",entry,file=sys.stderr)
        return 1
    scope="tracked + untracked candidates" if args.include_untracked else "tracked"
    print(f"Nykra OSS {scope} hygiene passed: {len(paths)} files, "
          f"{len(REQUIRED)} required tracked artifacts, no known credential signatures")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
