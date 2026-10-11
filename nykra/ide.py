"""Discover compatible editor CLIs and build/install a single managed VS Code extension.

The editor extension is passive and cannot identify hidden agent decisions.
No installation changes are made without an explicit 'ide install' request.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import __version__
from .store import NykraError, default_home

EXTENSION_ID = "nykra.nykra-observer"
IDE_TARGETS = {
    "vscode": ("code", "Microsoft VS Code"),
    "cursor": ("cursor", "Cursor"),
    "windsurf": ("windsurf", "Windsurf"),
    "vscodium": ("codium", "VSCodium"),
}
EXTENSION_DIR = Path(__file__).parent / "ide_extension"


def _candidates(name: str, app: str) -> list[Path]:
    candidates: list[Path] = []
    for command in (name, name + ".cmd"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        roots = [local / "Programs", Path(os.environ.get("ProgramFiles", "C:/Program Files")),
                 Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))]
        directory_names = (app, app.lower(), name, name.capitalize())
        for base in roots:
            for directory in directory_names:
                prefix = base / directory
                candidates.extend([prefix / "bin" / (name + ".cmd"),
                                   prefix / "resources" / "app" / "bin" / (name + ".cmd")])
    # Stable first hit only; never execute discovery candidates here.
    dedup = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            dedup.append(candidate)
    return dedup


def detect_ides() -> list[dict]:
    result = []
    for ident, (command, app) in IDE_TARGETS.items():
        found = next((candidate for candidate in _candidates(command, app)
                      if candidate.is_file()), None)
        result.append({
            "id": ident,
            "name": app,
            "cli_detected": found is not None,
            "cli": str(found) if found is not None else None,
            "capability": "cli_candidate_detected" if found else "installation_not_verified",
        })
    return result


def package_vsix(destination: Path | str | None = None) -> Path:
    if destination is None:
        destination = default_home() / "packages" / f"nykra-observer-{__version__}.vsix"
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    package = json.loads((EXTENSION_DIR / "package.json").read_text(encoding="utf-8"))
    if package.get("publisher") != "nykra" or package.get("name") != "nykra-observer":
        raise NykraError("unexpected IDE extension identity")
    version = package["version"]
    if version != __version__:
        raise NykraError("extension and Nykra core versions differ")
    content_types = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="json" ContentType="application/json"/>'
        '<Default Extension="js" ContentType="application/javascript"/>'
        '<Default Extension="txt" ContentType="text/plain"/>'
        '<Default Extension="md" ContentType="text/markdown"/>'
        '<Default Extension="xml" ContentType="text/xml"/>'
        '<Default Extension="vsixmanifest" ContentType="text/xml"/>'
        '</Types>'
    )
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata>
<Identity Id="nykra-observer" Version="{escape(version)}" Publisher="nykra" Language="en-US"/>
<DisplayName>Nykra Passive Observer</DisplayName>
<Description xml:space="preserve">Privacy-minimized local editor events for Nykra.</Description>
<Tags>local,observation,developer-tools</Tags>
<Categories>Other</Categories>
<GalleryFlags>Public</GalleryFlags>
</Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/>
<Assets>
<Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
<Asset Type="Microsoft.VisualStudio.Code.Content" Path="extension/extension.js" Addressable="true"/>
</Assets>
</PackageManifest>'''
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("extension.vsixmanifest", manifest)
        for filename in ("package.json", "extension.js", "LICENSE"):
            archive.write(EXTENSION_DIR / filename, arcname="extension/" + filename)
    return target


def manage_extension(action: str, *, target: str = "all", dry_run: bool = False) -> dict:
    if action not in ("install", "uninstall"):
        raise NykraError("action must be install or uninstall")
    if target != "all" and target not in IDE_TARGETS:
        raise NykraError("unknown IDE target")
    discovered = [item for item in detect_ides()
                  if (target == "all" or item["id"] == target)]
    chosen = [item for item in discovered if item["cli_detected"]]
    if not chosen:
        return {"action": action, "outcome": "no_compatible_editor_cli_detected",
                "changed": False, "editors": discovered}
    pkg = package_vsix() if action == "install" and not dry_run else None
    results = []
    for editor in chosen:
        command = ([editor["cli"], "--install-extension", str(pkg)]
                   if action == "install" else [editor["cli"], "--uninstall-extension", EXTENSION_ID])
        if dry_run:
            results.append({"editor": editor["id"], "status": "planned"})
            continue
        try:
            response = subprocess.run(command, capture_output=True, text=True,
                                      stdin=subprocess.DEVNULL, timeout=40, check=False)
            results.append({"editor": editor["id"], "status": "completed" if response.returncode == 0 else "failed",
                            "exit_code": response.returncode})
        except (OSError, subprocess.TimeoutExpired):
            results.append({"editor": editor["id"], "status": "unavailable"})
    return {
        "action": action, "changed": any(item["status"] == "completed" for item in results),
        "editors": results, "package": str(pkg) if pkg else None,
        "note": "Editor restart/reload may be required. This installs a passive IDE extension, not an agent control hook.",
    }
