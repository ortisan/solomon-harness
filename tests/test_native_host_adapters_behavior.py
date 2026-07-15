"""Behavioral contracts for the three native host adapter ports."""

from __future__ import annotations

import tomllib
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from solomon_harness.adapter_ownership import TEXT_END, TEXT_START
from solomon_harness.host_adapter_agy import AgyAdapter
from solomon_harness.host_adapter_claude import ClaudeAdapter
from solomon_harness.host_adapter_codex import CodexAdapter
from solomon_harness.host_adapter_common import (
    CAPABILITIES,
    HostCompileContext,
    HostInspectionContext,
    _Recorder,
    _RuntimeLayout,
    _Specialist,
    _Workflow,
    _runtime_layout,
)
from solomon_harness.host_adapter_contract import HostInspection, NativeHostAdapter
from solomon_harness.layout import HarnessPaths


def _contexts(root: Path) -> SimpleNamespace:
    paths = HarnessPaths(root)
    paths.rules.parent.mkdir(parents=True, exist_ok=True)
    paths.rules.write_text("# Canonical rules\n", encoding="utf-8")
    paths.pyproject.write_text("[project]\nname = 'consumer'\n", encoding="utf-8")
    mcp_server = paths.python_package / "mcp_server.py"
    mcp_server.parent.mkdir(parents=True, exist_ok=True)
    mcp_server.write_text("", encoding="utf-8")

    specialist_directory = paths.agents / "qa"
    role = specialist_directory / "agents" / "qa.md"
    role.parent.mkdir(parents=True, exist_ok=True)
    role.write_text("# QA\n\nValidate host parity.\n", encoding="utf-8")
    workflow_source = paths.workflows / "solomon-review.md"
    workflow_source.parent.mkdir(parents=True, exist_ok=True)
    workflow_source.write_text("# Review\n\nReview the change.\n", encoding="utf-8")

    rules_reference = paths.rules.relative_to(root).as_posix()
    paths.root_instructions.write_text(
        f"{TEXT_START}\nRead `{rules_reference}`.\n{TEXT_END}\n",
        encoding="utf-8",
    )
    runtime = _runtime_layout(False)
    recorder = _Recorder(root, {})
    compile_context = HostCompileContext(
        root=root,
        paths=paths,
        specialists=(
            _Specialist("qa", "Validate host parity.", specialist_directory),
        ),
        workflows=(
            _Workflow("review", "Review the change.", workflow_source),
        ),
        rules=paths.rules,
        runtime=runtime,
        recorder=recorder,
        mcp_command="uv",
    )
    inspect_context = HostInspectionContext(
        root=root,
        paths=paths,
        runtime=runtime,
        expected_specialists=("qa",),
        expected_workflows=("review",),
        agents_reference=paths.agents.relative_to(root).as_posix(),
        rules_reference=rules_reference,
        workflow_references={
            "review": workflow_source.relative_to(root).as_posix(),
        },
        shared_workflows=("review",),
        mcp_command="uv",
    )
    return SimpleNamespace(
        paths=paths,
        compile=compile_context,
        inspect=inspect_context,
        recorder=recorder,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("adapter", "specialist_state", "runtime_state"),
    [
        (AgyAdapter(), "active", "configured"),
        (ClaudeAdapter(), "active", "configured"),
        (CodexAdapter(), "pending_trust", "pending_trust"),
    ],
    ids=("agy", "claude", "codex"),
)
def test_native_adapter_compiles_and_inspects_its_complete_contract(
    tmp_path: Path,
    adapter: NativeHostAdapter,
    specialist_state: str,
    runtime_state: str,
) -> None:
    contexts = _contexts(tmp_path)

    adapter.compile(contexts.compile)
    inspection = adapter.inspect(contexts.inspect)

    assert set(inspection.capability_states) == CAPABILITIES
    assert inspection.capability_states["headless"] == "active"
    assert inspection.capability_states["instructions"] == "active"
    assert inspection.capability_states["specialists"] == specialist_state
    assert inspection.capability_states["workflows"] == "active"
    assert inspection.capability_states["session_start"] == runtime_state
    assert inspection.capability_states["pre_tool_guard"] == runtime_state
    assert inspection.capability_states["mcp"] == runtime_state
    assert inspection.specialists == ("qa",)
    assert inspection.workflows == ("review",)
    assert contexts.recorder.result().conflicts == ()


@pytest.mark.unit
@pytest.mark.parametrize("adapter", [AgyAdapter(), ClaudeAdapter(), CodexAdapter()])
def test_native_adapters_reject_foreign_contexts(adapter: NativeHostAdapter) -> None:
    with pytest.raises(TypeError):
        adapter.compile(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        adapter.inspect(object())  # type: ignore[arg-type]


@pytest.mark.unit
def test_host_contract_is_runtime_checkable_and_results_are_immutable() -> None:
    assert isinstance(AgyAdapter(), NativeHostAdapter)
    assert isinstance(ClaudeAdapter(), NativeHostAdapter)
    assert isinstance(CodexAdapter(), NativeHostAdapter)
    assert not isinstance(object(), NativeHostAdapter)

    inspection = HostInspection({"headless": "active"}, ("qa",), ("review",))
    with pytest.raises(FrozenInstanceError):
        inspection.specialists = ()  # type: ignore[misc]


@pytest.mark.integration
@pytest.mark.parametrize(
    "existing",
    [
        b"\xff",
        (
            b"# >>> solomon-harness managed adapter >>>\n"
            b"managed = true\n"
            b"# >>> solomon-harness managed adapter >>>\n"
        ),
        (
            b"[[hooks.PreToolUse]]\n"
            b"matcher = 'x'\n"
            b"[[hooks.PreToolUse.hooks]]\n"
            b"type = 'command'\n"
            b"command = 'python -I -m solomon_harness.cli host-hook pre-tool-use --host codex'\n"
            b"commandWindows = 'guard'\n"
            b"timeout = 30\n"
        ),
        b"[mcp_servers.solomon-memory]\ncommand = 'consumer-owned'\n",
    ],
    ids=("invalid-utf8", "invalid-markers", "unowned-hook", "unowned-mcp"),
)
def test_codex_compile_fails_closed_for_ambiguous_native_configuration(
    tmp_path: Path,
    existing: bytes,
) -> None:
    contexts = _contexts(tmp_path)
    config = contexts.paths.codex_config
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_bytes(existing)

    CodexAdapter().compile(contexts.compile)

    assert contexts.recorder.result().conflicts == (".codex/config.toml",)
    assert config.read_bytes() == existing


@pytest.mark.integration
def test_codex_compile_preserves_a_directory_at_the_config_boundary(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path)
    contexts.paths.codex_config.mkdir(parents=True)

    CodexAdapter().compile(contexts.compile)

    assert contexts.paths.codex_config.is_dir()
    assert contexts.recorder.result().conflicts == (".codex/config.toml",)


@pytest.mark.integration
def test_codex_compile_preserves_a_symlinked_config_boundary(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.toml"
    outside.write_text("consumer_owned = true\n", encoding="utf-8")
    config = contexts.paths.codex_config
    config.parent.mkdir(parents=True, exist_ok=True)
    config.symlink_to(outside)
    try:
        CodexAdapter().compile(contexts.compile)

        assert contexts.recorder.result().conflicts == (".codex/config.toml",)
        assert outside.read_text(encoding="utf-8") == "consumer_owned = true\n"
    finally:
        config.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


@pytest.mark.integration
def test_codex_inspection_reports_disabled_native_hooks_as_disabled(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path)
    adapter = CodexAdapter()
    adapter.compile(contexts.compile)
    config = contexts.paths.codex_config
    config.write_text(
        "[features]\nhooks = false\n\n" + config.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    inspection = adapter.inspect(contexts.inspect)

    assert inspection.capability_states["session_start"] == "disabled"
    assert inspection.capability_states["pre_tool_guard"] == "disabled"
    assert inspection.capability_states["mcp"] == "pending_trust"


@pytest.mark.integration
def test_codex_mcp_cwd_is_anchored_to_repository_root(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path)
    adapter = CodexAdapter()
    adapter.compile(contexts.compile)
    config = contexts.paths.codex_config
    document = tomllib.loads(config.read_text(encoding="utf-8"))
    server = document["mcp_servers"]["solomon-memory"]

    assert server["cwd"] == ".."
    assert adapter.inspect(contexts.inspect).capability_states["mcp"] == "pending_trust"

    config.write_text(
        config.read_text(encoding="utf-8").replace('cwd = ".."', 'cwd = "."'),
        encoding="utf-8",
    )

    assert adapter.inspect(contexts.inspect).capability_states["mcp"] == "unavailable"


@pytest.mark.integration
@pytest.mark.parametrize(
    "document",
    [
        "",
        "[",
        "mcp_servers = 'invalid'\nhooks = 'invalid'\n",
        "[mcp_servers]\nsolomon-memory = 'invalid'\n[hooks]\nPreToolUse = 'invalid'\n",
    ],
    ids=("empty", "malformed", "invalid-sections", "invalid-native-members"),
)
def test_codex_inspection_fails_closed_for_invalid_native_shapes(
    tmp_path: Path,
    document: str,
) -> None:
    contexts = _contexts(tmp_path)
    config = contexts.paths.codex_config
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(document, encoding="utf-8")

    inspection = CodexAdapter().inspect(contexts.inspect)

    assert inspection.capability_states["mcp"] == "unavailable"
    assert inspection.capability_states["session_start"] == "unavailable"
    assert inspection.capability_states["pre_tool_guard"] == "unavailable"


@pytest.mark.unit
def test_runtime_layouts_keep_source_and_consumer_projects_separate() -> None:
    source = _runtime_layout(True)
    consumer = _runtime_layout(False)

    assert isinstance(source, _RuntimeLayout)
    assert source.mcp_args()[3] == "."
    assert source.mcp_env()["UV_PROJECT_ENVIRONMENT"] == ".agents/solomon/state/venv"
    assert consumer.mcp_args()[3] == ".agents/solomon"
    assert consumer.mcp_env()["UV_PROJECT_ENVIRONMENT"] == "state/venv"
