# Nykra v0.4 — Windows per-user workstation runtime

**Status:** The development installer uses your existing Python 3.10+ interpreter; it is not yet a fully standalone executable. It requires **one installation command**, but does not require configuring individual agents, API keys, IDEs or MCP clients. Nykra v0.4 observes only the supported Rel.AI execution history. No other IDE is automatically integrated yet.

## Installation

From the Nykra repository:

```powershell
python -m nykra install
```

The command creates a private copy of the Nykra Python package in `%LOCALAPPDATA%\Nykra\runtime`, creates a login-start entry `Nykra.cmd` in the current user's Windows Startup directory, and launches the background observer. Administrator permission is not required. The background interpreter is `pythonw.exe` when available, and uses the same local Python installation used for setup.

The Rel.AI connector, MCP tool schemas, remote tunnel, and running Rel.AI app are **not modified or restarted**. The daemon auto-detects `~/.rel-ai-mcp/durable-state.sqlite`, observes **future** completed tool events through SQLite's read-only mode, and writes privacy-minimized metadata to Nykra's own local SQLite history.

The startup entry runs at the next Windows login. If the developer Python installation is removed or relocated, the background runtime must be repaired or later replaced by a bundled executable. Nykra currently does not implement automatic software updates, Windows service registration, fault-report upload, or a system-wide observer.

## Use

```powershell
python -m nykra doctor
python -m nykra background status
python -m nykra background stop
python -m nykra background start
python -m nykra activity --source relai-history --limit 20
```

`doctor` confirms the installed state, whether the supported Rel.AI database is discoverable, heartbeat health, and local history counts. It doesn't expose agent prompts or command output.

`background stop` is cooperative and waits for a graceful exit, without terminating other processes. Login autostart remains registered, so `background start` or the next login resumes the observer. Nykra uses an OS-level single-instance lock to prevent duplicate background loops if startup happens twice.

Rel.AI unavailable? The runtime waits without crashing or trying to install it. It begins observation when the supported database appears.

## Uninstall

```powershell
python -m nykra uninstall
```

This stops the background loop, removes **only** the Nykra-owned startup entry and installed runtime files, and leaves your Nykra history database in place. Nykra refuses to overwrite or delete a startup entry changed or owned by someone else. It also checks the OS lock rather than trusting potentially stale health data.

There is intentionally **no automatic purge of history**. If a user later wants to remove historical local records, those should be handled as a separate explicit deletion action.

## Limitations and boundaries

- **Passive observation only:** Tool successes are not treated as correct or superior solutions. Evaluated discovery requires an authorized execution controller using explicit metrics.
- **One-time Windows developer install:** Python must already be installed to run the installer and background runtime. Fully bundled installers, signed distributions and self-healing service management remain future milestones.
- **Agent agnosticism requires adapters:** Other agentic IDEs do not become automatically observable solely because Nykra is installed. The current passive observer is built specifically for Rel.AI's supported SQLite history projection.
- **No automatic recovery after process crash until next login** in this version; the runtime recovers from transient missing/locked Rel.AI history during its normal loop, but Windows login startup is its lifecycle restart mechanism.
- **No stealthy interception:** Nykra reads the authorized current-user Rel.AI state only. It does not capture encrypted MCP transport or hidden model reasoning.
- **Updates:** Re-running `python -m nykra install` performs a managed replacement after stopping a healthy running Nykra process. The installer requires its existing ownership manifest and refuses conflicting startup edits. Back up important local history before upgrades.
- **Privacy:** The background observer queries only selected scalar fields and never retrieves full event payloads. The Nykra SQLite history and local health file stay in the user's profile.

If `python -m nykra install` returns `runtime_not_ready`, run `python -m nykra doctor` to inspect status and verify that the Python executable saved by the installer still exists. Do not manually kill a process by PID based on an old heartbeat.
