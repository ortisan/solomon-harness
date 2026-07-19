"""Architecture fitness functions for native host adapter boundaries."""

from __future__ import annotations

import importlib.util
import ast
from importlib import import_module
from pathlib import Path
from typing import Any

from solomon_harness.host_adapter_contract import HostInspection
from solomon_harness.install_transaction import observe_install_mutations
from solomon_harness.payload_inventory import package_python_files


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _imports(module_name: str) -> set[str]:
    path = SOURCE_ROOT / (module_name.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
        elif isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
    return result


def _function_names(module_name: str) -> set[str]:
    path = SOURCE_ROOT / (module_name.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_each_host_has_an_independent_adapter_module() -> None:
    """A host schema change must have one host-owned module to edit."""

    modules = (
        "solomon_harness.host_adapter_agy",
        "solomon_harness.host_adapter_claude",
        "solomon_harness.host_adapter_codex",
    )

    missing = [name for name in modules if importlib.util.find_spec(name) is None]

    assert missing == []


def test_installed_payload_contains_the_complete_adapter_boundary() -> None:
    """A consumer install must receive the facade, port, support, and all hosts."""

    expected = {
        Path(f"solomon_harness/host_adapter_{name}.py")
        for name in ("agy", "claude", "codex", "common", "contract")
    }

    assert expected <= set(package_python_files(SOURCE_ROOT))


def test_host_modules_share_one_typed_adapter_contract() -> None:
    """The facade must depend on a stable host port, not concrete conditionals."""

    contract = importlib.util.find_spec("solomon_harness.host_adapter_contract")

    assert contract is not None


def test_adapter_port_names_the_compile_and_inspection_contexts() -> None:
    """The port must expose useful boundary types instead of opaque objects."""

    contract = import_module("solomon_harness.host_adapter_contract")
    adapter_type = contract.NativeHostAdapter

    assert adapter_type.compile.__annotations__["context"] == "HostCompileContext"
    assert adapter_type.inspect.__annotations__["context"] == "HostInspectionContext"


def test_each_host_adapter_satisfies_the_common_port() -> None:
    """Every concrete host must be substitutable behind the facade's port."""

    contract = import_module("solomon_harness.host_adapter_contract")
    adapter_type = getattr(contract, "NativeHostAdapter", None)

    assert adapter_type is not None
    adapters = [
        getattr(import_module(f"solomon_harness.host_adapter_{host}"), "ADAPTER", None)
        for host in ("agy", "claude", "codex")
    ]
    assert all(adapter is not None for adapter in adapters)
    assert all(isinstance(adapter, adapter_type) for adapter in adapters)


def test_facade_registers_all_hosts_through_the_common_port() -> None:
    """Adding orchestration must not reopen a host-name dispatch chain."""

    facade = import_module("solomon_harness.host_adapters")
    adapters = getattr(facade, "ADAPTERS", None)

    assert adapters is not None
    assert tuple(adapter.name for adapter in adapters) == facade.HOSTS


def test_dependency_direction_is_facade_to_hosts_to_common_contract() -> None:
    """Common support must never select a concrete host or import the facade."""

    common_imports = _imports("solomon_harness.host_adapter_common")
    host_modules = {
        f"solomon_harness.host_adapter_{host}" for host in ("agy", "claude", "codex")
    }

    assert common_imports.isdisjoint(host_modules)
    for host_module in host_modules:
        imports = _imports(host_module)
        assert "solomon_harness.host_adapters" not in imports
        assert imports.isdisjoint(host_modules - {host_module})


def test_facade_owns_compilation_and_inspection_orchestration() -> None:
    """The public entrypoints must compose adapters rather than hide in support."""

    facade_functions = _function_names("solomon_harness.host_adapters")

    assert {"compile_adapters", "inspect_capabilities"} <= facade_functions


def test_common_support_contains_no_host_specific_orchestration() -> None:
    """Host schemas and public orchestration belong outside neutral support."""

    common_functions = _function_names("solomon_harness.host_adapter_common")
    forbidden = {
        "compile_adapters",
        "inspect_capabilities",
        "_merge_agy_hooks",
        "_merge_claude_settings",
        "_merge_codex_config",
        "_valid_codex_hooks",
        "_valid_codex_mcp",
    }

    assert common_functions.isdisjoint(forbidden)


def test_compile_adapters_publishes_a_complete_design_contract() -> None:
    """The mutating public boundary must make its observable contract explicit."""

    facade = import_module("solomon_harness.host_adapters")
    contract = facade.compile_adapters.__doc__ or ""

    for clause in (
        "Preconditions:",
        "Postconditions:",
        "Invariants:",
        "Idempotency:",
        "Errors:",
    ):
        assert clause in contract


def test_compile_adapters_acquires_the_shared_install_operation_lock() -> None:
    """Direct host compilation must serialize with install and uninstall."""

    path = SOURCE_ROOT / "solomon_harness" / "host_adapters.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "compile_adapters"
    )
    contexts = [
        item.context_expr
        for node in ast.walk(function)
        if isinstance(node, ast.With)
        for item in node.items
    ]

    assert any(
        isinstance(context, ast.Call)
        and isinstance(context.func, ast.Name)
        and context.func.id == "install_operation_lock"
        for context in contexts
    )


def test_adapter_recorder_observes_directories_and_completed_writes(
    tmp_path: Path,
) -> None:
    """Rollback CAS observes safe parent creation and each published adapter."""

    common = import_module("solomon_harness.host_adapter_common")
    recorder = common._Recorder(tmp_path, {})
    generated = tmp_path / ".claude" / "agents" / "qa.md"
    merged = tmp_path / ".codex" / "config.toml"
    observed: list[Path] = []

    with observe_install_mutations(observed.append):
        recorder.write_generated(generated, "generated\n")
        recorder.write_generated(generated, "generated\n")
        recorder.write_merged(merged, "merged = true\n")
        recorder.write_merged(merged, "merged = true\n")

    assert observed == [
        tmp_path / ".claude",
        tmp_path / ".claude" / "agents",
        generated,
        tmp_path / ".codex",
        merged,
    ]


def test_compile_facade_delegates_once_to_each_registered_adapter(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The facade must compose hosts exclusively through ``NativeHostAdapter``."""

    core = tmp_path / ".agents" / "solomon"
    role = core / "agents" / "qa" / "agents" / "qa.md"
    role.parent.mkdir(parents=True)
    role.write_text("# QA\n\nQuality specialist.\n", encoding="utf-8")
    workflows = core / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "solomon-review.md").write_text(
        "# Review\n\nReview the change.\n", encoding="utf-8"
    )
    (core / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (core / "pyproject.toml").write_text("[project]\nname='consumer'\n", encoding="utf-8")
    runtime = core / "solomon_harness" / "mcp_server.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("", encoding="utf-8")
    (core / "manifest.json").write_text(
        '{"schema_version": 1, "entries": []}\n',
        encoding="utf-8",
    )

    calls: list[str] = []

    class RecordingAdapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def compile(self, context: object) -> None:
            assert context is not None
            calls.append(self.name)

        def inspect(self, context: object) -> HostInspection:
            assert context is not None
            return HostInspection({}, (), ())

    facade = import_module("solomon_harness.host_adapters")
    monkeypatch.setattr(
        facade,
        "ADAPTERS",
        tuple(RecordingAdapter(host) for host in facade.HOSTS),
    )

    facade.compile_adapters(tmp_path)

    assert calls == list(facade.HOSTS)
