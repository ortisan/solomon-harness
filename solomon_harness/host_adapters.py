"""Facade for compiling and inspecting native Solomon host adapters."""

import os
from pathlib import Path
from typing import Any

from solomon_harness.host_adapter_agy import ADAPTER as AGY_ADAPTER
from solomon_harness.host_adapter_claude import ADAPTER as CLAUDE_ADAPTER
from solomon_harness.host_adapter_codex import ADAPTER as CODEX_ADAPTER
from solomon_harness.host_adapter_common import (
    CAPABILITIES,
    HOSTS,
    AdapterCompileResult,
    HostCompileContext,
    HostInspectionContext,
    _CAPABILITY_STATES,
    _Recorder,
    _catalog,
    _load_previous_ownership,
    _overall_status,
    _reference,
    _runtime_layout,
    _skill_names,
    _workflow_skill,
    _write_marker_file,
)
from solomon_harness.host_adapter_contract import NativeHostAdapter
from solomon_harness.install_lock import (
    install_operation_lock,
    non_materializing_operation_lock,
)
from solomon_harness.install_transaction import current_install_root
from solomon_harness.layout import HarnessPaths


ADAPTERS: tuple[NativeHostAdapter, ...] = (
    AGY_ADAPTER,
    CLAUDE_ADAPTER,
    CODEX_ADAPTER,
)
_MCP_COMMAND = "uv"


def compile_adapters(project_root: os.PathLike[str] | str) -> AdapterCompileResult:
    """Compile all native adapters from the neutral catalog.

    Preconditions:
      ``project_root`` identifies a consumer install or a Git-proven Solomon
      source checkout with a readable specialist and workflow catalog.
    Postconditions:
      Every non-conflicting Claude, AGY, and Codex surface matches the neutral
      catalog; unrelated host configuration and user-owned bytes are retained.
    Invariants:
      Canonical workflow logic remains below ``.agents/solomon`` and adapters
      contain only native metadata, configuration, and references to that core.
    Idempotency:
      Repeating the call with unchanged inputs changes no bytes or modes and
      reports ``changed=False``.
    Errors:
      Missing catalogs raise ``FileNotFoundError``; unsafe paths and malformed
      managed state raise ``ValueError`` or ``RuntimeError``; ownership drift is
      returned in ``AdapterCompileResult.conflicts`` without overwriting it.
    """

    root = Path(project_root).resolve()
    with non_materializing_operation_lock(root):
        recorder = _Recorder(root, _load_previous_ownership(root))
        active_root = current_install_root()
        installed = HarnessPaths(root).manifest.is_file()
        if (
            not installed
            and active_root != root
            and not recorder._is_source_checkout()
        ):
            raise FileNotFoundError(
                "adapter compilation requires an installed manifest or a "
                "Git-proven solomon-harness source checkout"
            )
        with install_operation_lock(root):
            return _compile_adapters_locked(root)


def _compile_adapters_locked(
    project_root: os.PathLike[str] | str,
) -> AdapterCompileResult:
    root = Path(project_root).resolve()
    paths = HarnessPaths(root)
    specialists, workflows, rules = _catalog(root)
    recorder = _Recorder(root, _load_previous_ownership(root))
    runtime = _runtime_layout(recorder._is_source_checkout())

    _write_marker_file(
        recorder,
        paths.root_instructions,
        (
            f"The Solomon rules are in `{_reference(root, rules)}`. "
            "Read that file completely before starting work."
        ),
    )
    for workflow in workflows:
        directory = f"solomon-{workflow.name}"
        recorder.write_generated(
            paths.shared_skills / directory / "SKILL.md",
            _workflow_skill(workflow, root),
        )

    context = HostCompileContext(
        root=root,
        paths=paths,
        specialists=tuple(specialists),
        workflows=tuple(workflows),
        rules=rules,
        runtime=runtime,
        recorder=recorder,
        mcp_command=_MCP_COMMAND,
    )
    for adapter in ADAPTERS:
        adapter.compile(context)
    return recorder.result()


def inspect_capabilities(
    project_root: os.PathLike[str] | str,
) -> dict[str, dict[str, Any]]:
    """Inspect configured host capabilities without mutating the project."""

    root = Path(project_root).resolve()
    paths = HarnessPaths(root)
    try:
        specialists, workflows, rules = _catalog(root)
    except FileNotFoundError:
        specialists = []
        workflows = []
        rules = paths.rules
    recorder = _Recorder(root, {})
    runtime = _runtime_layout(recorder._is_source_checkout())
    expected_specialists = tuple(sorted(item.name for item in specialists))
    expected_workflows = tuple(sorted(item.name for item in workflows))
    agents_reference = _reference(root, paths.resolve_agents())
    rules_reference = _reference(root, rules)
    workflow_references = {
        item.name: _reference(root, item.source) for item in workflows
    }
    context = HostInspectionContext(
        root=root,
        paths=paths,
        runtime=runtime,
        expected_specialists=expected_specialists,
        expected_workflows=expected_workflows,
        agents_reference=agents_reference,
        rules_reference=rules_reference,
        workflow_references=workflow_references,
        shared_workflows=_skill_names(paths.shared_skills, workflow_references),
        mcp_command=_MCP_COMMAND,
    )

    result: dict[str, dict[str, Any]] = {}
    for adapter in ADAPTERS:
        inspection = adapter.inspect(context)
        states = dict(inspection.capability_states)
        if not set(states.values()) <= _CAPABILITY_STATES:
            raise AssertionError("unknown capability activation state")
        capabilities = {
            capability
            for capability, state in states.items()
            if state not in {"disabled", "unavailable"}
        }
        result[adapter.name] = {
            "capabilities": capabilities,
            "capability_states": states,
            "status": _overall_status(states),
            "specialists": inspection.specialists,
            "workflows": inspection.workflows,
        }
    return result


__all__ = [
    "ADAPTERS",
    "CAPABILITIES",
    "HOSTS",
    "AdapterCompileResult",
    "compile_adapters",
    "inspect_capabilities",
]
