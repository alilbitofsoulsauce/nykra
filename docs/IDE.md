# Nykra v0.5 — VS Code-family IDE observation

Nykra provides a passive extension for editors with compatible VS Code extension APIs. It observes document saves inside trusted workspaces and the completion outcomes of IDE tasks, using supported editor lifecycle events.

**Recorded fields:** editor family, pseudonymous SHA-256-derived workspace ID, unique event ID, event type, succeeded/failed outcome, and duration (when available). Nykra does not collect filenames, paths, file contents, prompts, task names, terminal commands or their outputs. Workspace hashes are pseudonymous, not guaranteed anonymous. It cannot determine whether an edit was performed by a human or by an AI agent.

## IDE discovery and installation

After installing or upgrading Nykra, use:

~~~powershell
python -m nykra install
python -m nykra doctor
python -m nykra ide scan
~~~

One explicit command installs the same extension into all detected compatible IDE CLIs without per-agent configuration:

~~~powershell
python -m nykra ide install
~~~

For a dry run, use python -m nykra ide install --dry-run. Nykra refuses to guess an editor installation merely from a leftover user profile directory. Supported candidate CLIs are VS Code, Cursor, Windsurf and VSCodium, but actual editor compatibility depends on each installed version and its extension host. A reload may be needed.

When no compatible CLI is available, create an extension package with:

~~~powershell
python -m nykra ide package
~~~

That returns a local .vsix path, which can be installed manually in a compatible editor using **Extensions → Install from VSIX…**. Without a supported install interface, installation cannot be fully automatic. No editor CLI was found in the current workstation's initial scan, so v0.5 tests do not establish a production IDE installation.

To remove the exact Nykra extension from detected editors:

~~~powershell
python -m nykra ide uninstall
~~~

This targets only the extension ID nykra.nykra-observer. Other extensions and model/agent settings are untouched.

## Runtime and security

The extension works only in a trusted, open workspace. It ignores untitled documents, files outside the workspace and task outcomes with unknown exit codes. Events are written atomically into the local Nykra IDE inbox and consumed by its installed background runtime. The inbox enforces exact whitelisted fields and bounds queued files to prevent unlimited growth. No cloud service, network port, remote MCP registration or external model API is required.

Nykra's existing Rel.AI observer continues independently. Neither IDE saves nor generic tool completions are converted into scored discovery attempts.

**Uninstall note:** Uninstalling Nykra's Windows runtime removes its managed startup entry but does not automatically remove IDE extensions or the user's accumulated history. Run the IDE uninstall command beforehand if desired.

## Research boundary

This integration provides passive execution context, not hidden agent deliberation or active recursive self-improvement. A future supervised host controller must explicitly supply branching relationships, objective evaluations and tested policy decisions.
