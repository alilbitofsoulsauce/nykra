"""Reversible, source-level Nykra integration for a compatible Rel.AI host.

Run against a *development source checkout*, not a running Electron application
or its ASAR bundle. Attaches to the existing host lifecycle listener; does not
change MCP schemas or require any agent-specific config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

PATCH_VERSION = 1
ENTRY = Path("src/tools/callTool.js")
BRIDGE = Path("src/tools/nykraBridge.mjs")
STATE = Path("src/tools/.nykra-integration.json")
IMPORT_ANCHOR = b"import { buildToolActivityDetails } from '../taskObservability.js';"
BOOT_ANCHOR = b"bindTaskHistoryActivityPersistence(onToolActivity, readConfig);"
IMPORT_MARKER = b"// NYKRA_HOST_INTEGRATION_IMPORT_V1"
BOOT_MARKER = b"// NYKRA_HOST_INTEGRATION_START_V1"
IMPORT_LINE = b"import { attachRelaiBridge } from './nykraBridge.mjs'; " + IMPORT_MARKER
BOOT_LINES = (
    BOOT_MARKER + b"\n"
    b"try {\n"
    b"  // The local observer is best-effort; tool execution must remain independent.\n"
    b"  attachRelaiBridge(onToolActivity);\n"
    b"} catch {\n"
    b"  // Missing or unavailable Nykra never blocks the MCP execution runtime.\n"
    b"}\n"
    b"// NYKRA_HOST_INTEGRATION_END_V1"
)


class HostIntegrationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(prefix=".nykra-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as writer:
            writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _check_host(root: Path) -> tuple[Path, Path, Path, bytes]:
    root = root.expanduser().resolve()
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        raise HostIntegrationError("Not a Rel.AI source checkout: package.json absent")
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise HostIntegrationError("Rel.AI package metadata cannot be read") from exc
    if pkg.get("name") != "rel-ai-mcp":
        raise HostIntegrationError("Unsupported host: package name is not rel-ai-mcp")
    entry, bridge, state = root / ENTRY, root / BRIDGE, root / STATE
    if not entry.is_file():
        raise HostIntegrationError("Unsupported host: missing src/tools/callTool.js")
    return entry, bridge, state, entry.read_bytes()


def inspect(root: Path) -> dict[str, object]:
    entry, bridge, state, original = _check_host(root)
    installed = state.exists()
    if installed:
        if not bridge.is_file():
            raise HostIntegrationError("Partial install: bridge missing")
        meta = json.loads(state.read_text(encoding="utf-8"))
        if not (IMPORT_MARKER in original and BOOT_MARKER in original):
            raise HostIntegrationError("Partial install: hooks missing")
        if digest(original) != meta["patched_sha256"] or digest(bridge.read_bytes()) != meta["bridge_sha256"]:
            raise HostIntegrationError("Host integration was modified; refusing unsafe overwrite")
    elif IMPORT_MARKER in original or BOOT_MARKER in original or bridge.exists():
        raise HostIntegrationError("Unmanaged or partially patched host; refusing overwrite")
    elif original.count(IMPORT_ANCHOR) != 1 or original.count(BOOT_ANCHOR) != 1:
        raise HostIntegrationError("Unsupported host version: Nykra anchors not found exactly once")
    return {
        "host": str(root.resolve()),
        "state": "integrated" if installed else "compatible",
        "instrumented_tool_surface": "unchanged",
        "agent_configuration_required": False,
        "running_process_modified": False,
    }


def apply(root: Path) -> dict[str, object]:
    root = root.expanduser().resolve()
    report = inspect(root)
    if report["state"] == "integrated":
        return {**report, "changed": False}
    entry, bridge, state, original = _check_host(root)
    template = Path(__file__).with_name("bridge.mjs")
    if not template.is_file():
        raise HostIntegrationError("Nykra bridge.mjs is missing")
    bridge_data = template.read_bytes()
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    changed = original.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + newline + IMPORT_LINE)
    changed = changed.replace(BOOT_ANCHOR, BOOT_ANCHOR + newline + BOOT_LINES.replace(b"\n", newline))
    if changed == original:
        raise HostIntegrationError("No changes generated")
    metadata = {
        "version": PATCH_VERSION,
        "entry": ENTRY.as_posix(),
        "bridge": BRIDGE.as_posix(),
        "original_sha256": digest(original),
        "patched_sha256": digest(changed),
        "bridge_sha256": digest(bridge_data),
    }
    # Write new bridge first; if the entry edit fails, revert only our new file.
    _atomic(bridge, bridge_data)
    try:
        _atomic(entry, changed)
        _atomic(state, (json.dumps(metadata, indent=2) + "\n").encode("utf-8"))
    except Exception:
        if digest(entry.read_bytes()) == digest(changed):
            _atomic(entry, original)
        if bridge.is_file() and digest(bridge.read_bytes()) == digest(bridge_data):
            bridge.unlink()
        raise
    return {**inspect(root), "changed": True}


def remove(root: Path) -> dict[str, object]:
    root = root.expanduser().resolve()
    report = inspect(root)
    if report["state"] != "integrated":
        return {**report, "changed": False}
    entry, bridge, state, patched = _check_host(root)
    meta = json.loads(state.read_text(encoding="utf-8"))
    newline = b"\r\n" if b"\r\n" in patched else b"\n"
    original = patched.replace(newline + IMPORT_LINE, b"", 1)
    original = original.replace(newline + BOOT_LINES.replace(b"\n", newline), b"", 1)
    if digest(original) != meta["original_sha256"]:
        raise HostIntegrationError("Refusing removal: original content cannot be verified")
    _atomic(entry, original)
    bridge.unlink()
    state.unlink()
    return {**inspect(root), "changed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reversible Nykra integration for a Rel.AI source checkout")
    parser.add_argument("--host", type=Path, required=True, help="path to a Rel.AI source repository, not a running app")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="install Nykra host hook into checkout")
    action.add_argument("--remove", action="store_true", help="remove an unchanged Nykra host hook")
    args = parser.parse_args()
    try:
        result = apply(args.host) if args.apply else remove(args.host) if args.remove else inspect(args.host)
        print(json.dumps(result, indent=2))
        return 0
    except (HostIntegrationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
