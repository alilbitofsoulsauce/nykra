"""Portable host-driver contract and truthful per-agent capability discovery.

Nykra Core does not depend on Rel.AI. Only the Rel.AI-specific driver currently
executes the complete supervised agent turn protocol. Other discovered runtimes
are NOT reported as connected until their native adapter has been verified.
"""
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable

from .store import HistoryStore, NykraError


@dataclass(frozen=True)
class DriverCapabilities:
    id: str
    display_name: str
    detected: bool
    integration_level: str  # none, observer, supervised, controlled
    observation: bool
    interactive_revisions: bool
    objective_evaluation: bool
    autonomous_generation: bool
    auto_policy_application: bool
    implementation: str
    qualification: str

    def public(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class AgentDriver(Protocol):
    """Portable, approval-gated supervised turn contract.

    Execution and inference must remain owned by each authorized host.
    Any future vendor-native adapter should implement this shape.
    """
    def start(self, *, task_id: str, policy: str = "depth",
              budget: int = 4, max_seconds: float = 1200,
              threshold: float = 1.0, trial_id: str | None = None,
              task_key: str | None = None, approval: bool = False) -> dict: ...
    def next(self, session_id: str) -> dict: ...
    def submit(self, session_id: str, *, source: str,
               approval: bool = False) -> dict: ...
    def abort(self, session_id: str, *, approval: bool = False) -> dict: ...


_VENDOR_BINARIES = (
    ("codex", "Codex", "codex", "Official SDK/CLI available; no native Nykra turn adapter yet."),
    ("claude", "Claude Code", "claude", "Agent SDK/CLI possible; no native Nykra turn adapter yet."),
    ("opencode", "OpenCode", "opencode", "SDK/CLI possible; authenticated inference NOT verified here."),
    ("gemini", "Gemini CLI", "gemini", "CLI/hooks possible; no native Nykra turn adapter yet."),
    ("cursor", "Cursor", "cursor", "IDE CLI is not a verified unattended Nykra agent driver."),
)


def scan_drivers(*, relai_database_detected: bool | None = None) -> dict:
    if relai_database_detected is None:
        from .relai_history import default_relai_database
        relai_database_detected = default_relai_database().is_file()
    entries = [
        DriverCapabilities(
            id="relai", display_name="Rel.AI (connected ChatGPT)", detected=relai_database_detected,
            integration_level="supervised" if relai_database_detected else "none",
            observation=relai_database_detected,
            interactive_revisions=relai_database_detected,
            objective_evaluation=relai_database_detected,
            autonomous_generation=False, auto_policy_application=False,
            implementation="verified_local_adapter",
            qualification=(
                "Working in an authorized connected ChatGPT turn; Rel.AI MCP alone "
                "does not expose independent model-completion calls."
            ),
        ).public()
    ]
    for key, title, command, caution in _VENDOR_BINARIES:
        present = shutil.which(command) is not None
        entries.append(DriverCapabilities(
            id=key, display_name=title, detected=present,
            integration_level="none", observation=False,
            interactive_revisions=False, objective_evaluation=False,
            autonomous_generation=False, auto_policy_application=False,
            implementation="discovery_only",
            qualification=caution + " Binary detection is not authentication or capability verification.",
        ).public())
    return {
        "core": "agent_independent",
        "contract": "AgentDriver.v1",
        "workflow_v22": {
            "portable_protocol": "start/next/submit/finalize JSON source patch turns",
            "relai_supervised_host": True,
            "codex_readonly_proposal_provider": "available only when explicitly authorized and locally authenticated",
            "native_vendor_agentdriver_v1_adapter_proven": False,
            "arbitrary_multifile_repository_edits": False,
            "qualification": "Real upstream Git patch and Docker grading are limited to enumerated fixed tasks; no general uplift measured.",
        },
        "drivers": entries,
        "warning": (
            "Discovery is not integration: only Rel.AI has the verified supervised "
            "turn adapter. No detected agent is automatically controlled or patched."
        ),
    }


def get_driver(driver_id: str, store: HistoryStore) -> AgentDriver:
    if driver_id != "relai":
        raise NykraError(
            "native driver not implemented; discovery is not permission or integration"
        )
    from .relai_agent import RelaiAgent
    adapter = RelaiAgent(store)
    if not isinstance(adapter, AgentDriver):
        raise NykraError("Rel.AI adapter does not implement the shared driver contract")
    return adapter
