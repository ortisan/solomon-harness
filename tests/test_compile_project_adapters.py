"""Transactional compile contracts for an installed consumer repository."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from solomon_harness import curator
from solomon_harness.bootstrap import scaffold_new_agent
from solomon_harness.agent_selection import discover_agents
from solomon_harness.install_layout import (
    InstallConflictError,
    compile_project_adapters,
    install_project,
    register_agent_extension,
)
from solomon_harness.install_transaction import record_install_mutation
from solomon_harness.host_adapters import compile_adapters as compile_host_adapters
from solomon_harness.layout import HarnessPaths


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    result: dict[str, tuple[bytes, int, int]] = {}
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == ".agents/solomon/state/install.lock":
            continue
        info = path.stat()
        result[relative] = (
            path.read_bytes(),
            stat.S_IMODE(info.st_mode),
            info.st_mtime_ns,
        )
    return result


def _manifest_entries(root: Path) -> dict[str, dict[str, object]]:
    document = json.loads(HarnessPaths(root).manifest.read_text(encoding="utf-8"))
    return {entry["path"]: entry for entry in document["entries"]}


def _add_specialist(root: Path, name: str = "local_specialist") -> None:
    directory = HarnessPaths(root).agents / name
    role = directory / "agents" / f"{name}.md"
    role.parent.mkdir(parents=True)
    role.write_text(f"# {name}\n\nA local specialist.\n", encoding="utf-8")


@pytest.mark.integration
def test_installed_payload_compiles_twice_without_changing_any_state(tmp_path: Path) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    before = _snapshot(tmp_path)

    first = compile_project_adapters(tmp_path)
    after_first = _snapshot(tmp_path)
    second = compile_project_adapters(tmp_path)

    assert first.changed is False
    assert first.conflicts == ()
    assert first.blocking_conflicts == ()
    assert second.changed is False
    assert _snapshot(tmp_path) == after_first == before


@pytest.mark.integration
def test_installed_generator_entrypoint_targets_the_consumer_and_is_idempotent(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    paths = HarnessPaths(tmp_path)
    script = paths.scripts / "generate-integrations.py"
    environment = dict(os.environ)
    environment["UV_PROJECT_ENVIRONMENT"] = str(paths.state / "venv")
    command = [
        "uv",
        "run",
        "--frozen",
        "--project",
        str(paths.solomon),
        "python",
        "-I",
        str(script),
    ]

    warmup = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert warmup.returncode == 0, warmup.stdout + warmup.stderr
    assert not (paths.solomon / ".agents").exists()
    before = _snapshot(tmp_path)
    first = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    after_first = _snapshot(tmp_path)
    second = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert "Claude, AGY, and Codex" in first.stdout
    assert _snapshot(tmp_path) == after_first == before
    assert not (paths.solomon / ".agents").exists()

    paths.manifest.unlink()
    missing_manifest = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert missing_manifest.returncode == 1
    assert "manifest" in missing_manifest.stderr.lower()
    assert not (paths.solomon / ".agents").exists()


@pytest.mark.integration
def test_compile_updates_only_adapter_manifest_entries_and_is_idempotent(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    before_entries = _manifest_entries(tmp_path)
    _add_specialist(tmp_path)

    first = compile_project_adapters(tmp_path)
    after_entries = _manifest_entries(tmp_path)
    second = compile_project_adapters(tmp_path)

    assert first.changed is True
    assert first.conflicts == ()
    assert second.changed is False
    assert {
        path: entry
        for path, entry in after_entries.items()
        if entry["owner"] != "adapter"
    } == {
        path: entry
        for path, entry in before_entries.items()
        if entry["owner"] != "adapter"
    }
    assert {
        ".agents/agents/local_specialist/agent.md",
        ".claude/agents/local_specialist.md",
        ".codex/agents/local_specialist.toml",
    } <= set(after_entries)


@pytest.mark.integration
def test_scaffold_reconciles_a_real_installed_catalog_across_all_hosts(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)

    scaffold_new_agent(
        str(tmp_path),
        "consumer_specialist",
        "A consumer-owned specialist.",
    )
    entries = _manifest_entries(tmp_path)

    assert {
        ".agents/agents/consumer_specialist/agent.md",
        ".claude/agents/consumer_specialist.md",
        ".codex/agents/consumer_specialist.toml",
    } <= set(entries)
    assert all(
        (tmp_path / relative).is_file()
        for relative in (
            ".agents/agents/consumer_specialist/agent.md",
            ".claude/agents/consumer_specialist.md",
            ".codex/agents/consumer_specialist.toml",
        )
    )


@pytest.mark.integration
def test_broker_agent_registers_in_installed_catalog_without_git_or_pr(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test: install harness"],
        cwd=tmp_path,
        check=True,
    )
    paths = HarnessPaths(tmp_path)
    before_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    before_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=tmp_path, text=True
    ).strip()
    before_refs = subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"],
        cwd=tmp_path,
        text=True,
    )
    before_rules = paths.rules.read_bytes()
    before_entries = _manifest_entries(tmp_path)
    github_calls: list[list[str]] = []

    def github_runner(arguments: list[str]) -> object:
        github_calls.append(arguments)
        raise AssertionError("agent registration must not call GitHub")

    with (
        patch.object(
            curator,
            "apply_proposal",
            side_effect=AssertionError("agent registration must not use the PR path"),
        ) as apply_proposal,
        patch(
            "solomon_harness.host_adapters.compile_adapters",
            wraps=compile_host_adapters,
        ) as compile_adapters,
        patch("solomon_harness.tools.database_client.DatabaseClient") as database,
    ):
        agent_path = curator.broker_agent(
            str(tmp_path),
            "consumer_specialist",
            "Consumer Specialist",
            "Owns consumer-specific delivery work.",
            ["Handle consumer-specific delivery work"],
            gh_runner=github_runner,
            issue_id="240",
        )

    expected_agent = paths.agents / "consumer_specialist"
    after_entries = _manifest_entries(tmp_path)
    assert agent_path == os.fspath(expected_agent)
    assert (expected_agent / "agents" / "consumer_specialist.md").is_file()
    assert not (tmp_path / "agents" / "consumer_specialist").exists()
    assert "consumer_specialist" in discover_agents(str(tmp_path))
    assert paths.rules.read_bytes() == before_rules
    assert {
        path: entry
        for path, entry in after_entries.items()
        if entry["owner"] != "adapter"
    } == {
        path: entry
        for path, entry in before_entries.items()
        if entry["owner"] != "adapter"
    }
    assert {
        ".agents/agents/consumer_specialist/agent.md",
        ".claude/agents/consumer_specialist.md",
        ".codex/agents/consumer_specialist.toml",
    } <= set(after_entries)
    assert all(
        after_entries[path]["owner"] == "adapter"
        for path in (
            ".agents/agents/consumer_specialist/agent.md",
            ".claude/agents/consumer_specialist.md",
            ".codex/agents/consumer_specialist.toml",
        )
    )
    assert not any(
        path.startswith(".agents/solomon/agents/consumer_specialist/")
        for path in after_entries
    )
    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip() == before_head
    assert subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=tmp_path, text=True
    ).strip() == before_branch
    assert subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"],
        cwd=tmp_path,
        text=True,
    ) == before_refs
    assert github_calls == []
    apply_proposal.assert_not_called()
    compile_adapters.assert_called_once_with(tmp_path)
    database.assert_called_once_with(harness_dir=os.fspath(tmp_path))

    upgrade = install_project(tmp_path, source_root=SOURCE_ROOT)
    upgraded_entries = _manifest_entries(tmp_path)
    assert upgrade.blocking_conflicts == ()
    assert (expected_agent / "agents" / "consumer_specialist.md").is_file()
    assert "consumer_specialist" in discover_agents(str(tmp_path))
    assert paths.rules.read_bytes() == before_rules
    assert not any(
        path.startswith(".agents/solomon/agents/consumer_specialist/")
        for path in upgraded_entries
    )
    assert all(
        upgraded_entries[path]["owner"] == "adapter"
        for path in (
            ".agents/agents/consumer_specialist/agent.md",
            ".claude/agents/consumer_specialist.md",
            ".codex/agents/consumer_specialist.toml",
        )
    )


@pytest.mark.integration
def test_broker_agent_rolls_back_source_adapters_and_manifest_on_conflict(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    existing = HarnessPaths(tmp_path).agents / "existing_consumer"
    existing_role = existing / "agents" / "existing_consumer.md"
    existing_role.parent.mkdir(parents=True)
    existing_role.write_text("# Existing consumer\n", encoding="utf-8")
    preserved = tmp_path / ".claude" / "agents" / "conflict_specialist.md"
    preserved.write_text("user-owned adapter\n", encoding="utf-8")
    before = _snapshot(tmp_path)

    with pytest.raises(InstallConflictError, match="adapter conflicts"):
        curator.broker_agent(
            str(tmp_path),
            "conflict_specialist",
            "Conflict Specialist",
            "Exercises registration rollback.",
            ["Exercise registration rollback"],
        )

    assert _snapshot(tmp_path) == before
    assert preserved.read_text(encoding="utf-8") == "user-owned adapter\n"
    assert not (HarnessPaths(tmp_path).agents / "conflict_specialist").exists()
    assert not (
        tmp_path / ".agents" / "agents" / "conflict_specialist" / "agent.md"
    ).exists()
    assert not (
        tmp_path / ".codex" / "agents" / "conflict_specialist.toml"
    ).exists()
    assert not (existing / "main.py").exists()
    assert not (existing / ".agent" / "config.json").exists()


@pytest.mark.integration
def test_broker_agent_preserves_an_external_write_when_registration_fails(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    paths = HarnessPaths(tmp_path)
    persona = paths.agents / "external_specialist" / "persona.md"

    def external_write_then_fail(_root: str) -> object:
        persona.write_text("external writer\n", encoding="utf-8")
        raise RuntimeError("adapter compilation failed")

    with (
        patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=external_write_then_fail,
        ),
        pytest.raises(InstallConflictError, match="Rollback preserved paths"),
    ):
        curator.broker_agent(
            str(tmp_path),
            "external_specialist",
            "External Specialist",
            "Exercises compare-and-swap rollback.",
            ["Exercise compare-and-swap rollback"],
        )

    assert persona.read_text(encoding="utf-8") == "external writer\n"


@pytest.mark.integration
def test_broker_agent_rolls_back_a_partial_scaffold_file_write(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    before = _snapshot(tmp_path)

    def fail_after_partial_write(stream, payload: bytes) -> None:
        stream.write(payload[:8])
        stream.flush()
        raise OSError("disk full")

    with (
        patch(
            "solomon_harness.install_transaction._write_install_payload",
            side_effect=fail_after_partial_write,
        ),
        pytest.raises(OSError, match="disk full"),
    ):
        curator.broker_agent(
            str(tmp_path),
            "partial_specialist",
            "Partial Specialist",
            "Exercises atomic scaffold publication.",
            ["Exercise atomic scaffold publication"],
        )

    assert _snapshot(tmp_path) == before
    assert not (HarnessPaths(tmp_path).agents / "partial_specialist").exists()


@pytest.mark.integration
def test_broker_agent_does_not_claim_an_external_pre_checkpoint_write(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    paths = HarnessPaths(tmp_path)
    persona = paths.agents / "racing_specialist" / "persona.md"
    preserved = tmp_path / ".claude" / "agents" / "racing_specialist.md"
    preserved.write_text("user-owned adapter\n", encoding="utf-8")

    from solomon_harness import install_transaction

    original = install_transaction.record_install_file_publication

    def external_before_checkpoint(path, publication) -> None:
        if path == persona:
            path.write_text("external writer\n", encoding="utf-8")
        original(path, publication)

    with (
        patch.object(
            install_transaction,
            "record_install_file_publication",
            side_effect=external_before_checkpoint,
        ),
        pytest.raises(InstallConflictError, match="Rollback preserved paths"),
    ):
        curator.broker_agent(
            str(tmp_path),
            "racing_specialist",
            "Racing Specialist",
            "Exercises publication proof rollback.",
            ["Exercise publication proof rollback"],
        )

    assert persona.read_text(encoding="utf-8") == "external writer\n"


@pytest.mark.integration
@pytest.mark.parametrize("symlink_parent", [False, True])
def test_registration_rejects_symlinked_scaffold_content(
    tmp_path: Path,
    symlink_parent: bool,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    paths = HarnessPaths(tmp_path)
    agent = paths.agents / "symlink_specialist"
    (agent / "agents").mkdir(parents=True)
    (agent / "skills").mkdir()
    (agent / "agents" / "symlink_specialist.md").write_text(
        "# Symlink Specialist\n",
        encoding="utf-8",
    )
    (agent / "skills" / "scope_and_mandate.md").write_text(
        "# Scope\n",
        encoding="utf-8",
    )
    (agent / "main.py").write_text("\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as external_directory:
        external = Path(external_directory)
        if symlink_parent:
            (external / "config.json").write_text("{}\n", encoding="utf-8")
            (agent / ".agent").symlink_to(external, target_is_directory=True)
            (agent / "persona.md").write_text("# Persona\n", encoding="utf-8")
        else:
            (agent / ".agent").mkdir()
            (agent / ".agent" / "config.json").write_text("{}\n", encoding="utf-8")
            external_persona = external / "persona.md"
            external_persona.write_text("# External persona\n", encoding="utf-8")
            (agent / "persona.md").symlink_to(external_persona)

        with pytest.raises(InstallConflictError, match="symlink"):
            register_agent_extension(
                tmp_path,
                "symlink_specialist",
                lambda _path: None,
            )


@pytest.mark.integration
def test_broker_agent_refuses_direct_registration_in_a_source_checkout(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    source_markers = (
        Path("pyproject.toml"),
        Path("agents/AGENTS.md"),
        Path("solomon_harness/__init__.py"),
        Path("solomon_harness/mcp_server.py"),
        Path("scripts/generate-integrations.py"),
    )
    for relative in source_markers:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_ROOT / relative, destination)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "add", "--", *(str(path) for path in source_markers)],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "test: source checkout"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "scripts" / "generate-integrations.py").unlink()
    subprocess.run(
        [
            "git",
            "update-index",
            "--force-remove",
            "--",
            "scripts/generate-integrations.py",
        ],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer-lookalike"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", "pyproject.toml"],
        cwd=tmp_path,
        check=True,
    )

    with pytest.raises(InstallConflictError, match="source checkout"):
        curator.broker_agent(
            str(tmp_path),
            "source_specialist",
            "Source Specialist",
            "Must use reviewed source development.",
            ["Use reviewed source development"],
        )

    assert not (HarnessPaths(tmp_path).agents / "source_specialist").exists()


@pytest.mark.integration
def test_compile_removes_only_unchanged_stale_adapter_entries(tmp_path: Path) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    _add_specialist(tmp_path)
    compile_project_adapters(tmp_path)
    custom = HarnessPaths(tmp_path).agents / "local_specialist"
    for path in sorted(custom.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    custom.rmdir()

    result = compile_project_adapters(tmp_path)
    entries = _manifest_entries(tmp_path)

    assert result.conflicts == ()
    assert set(result.removed) == {
        ".agents/agents/local_specialist/agent.md",
        ".claude/agents/local_specialist.md",
        ".codex/agents/local_specialist.toml",
    }
    assert not set(result.removed) & set(entries)
    assert all(not (tmp_path / path).exists() for path in result.removed)


@pytest.mark.integration
def test_compile_preserves_a_modified_stale_adapter_as_a_conflict(tmp_path: Path) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    _add_specialist(tmp_path)
    compile_project_adapters(tmp_path)
    custom = HarnessPaths(tmp_path).agents / "local_specialist"
    for path in sorted(custom.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    custom.rmdir()
    modified = tmp_path / ".claude" / "agents" / "local_specialist.md"
    modified.write_text("user-owned\n", encoding="utf-8")

    result = compile_project_adapters(tmp_path)

    assert result.blocking_conflicts == (
        ".claude/agents/local_specialist.md",
    )
    assert modified.read_text(encoding="utf-8") == "user-owned\n"
    assert ".claude/agents/local_specialist.md" in _manifest_entries(tmp_path)


@pytest.mark.integration
def test_compile_rolls_back_every_adapter_and_manifest_on_renderer_failure(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    _add_specialist(tmp_path)
    before = _snapshot(tmp_path)

    def render_then_fail(root: Path) -> None:
        target = Path(root) / ".codex" / "agents" / "local_specialist.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("changed\n", encoding="utf-8")
        record_install_mutation(target)
        raise RuntimeError("renderer failed")

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=render_then_fail,
    ), pytest.raises(RuntimeError, match="renderer failed"):
        compile_project_adapters(tmp_path)

    assert _snapshot(tmp_path) == before


@pytest.mark.integration
def test_partial_temporary_adapter_write_never_replaces_or_leaks_into_project(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    _add_specialist(tmp_path)
    before = _snapshot(tmp_path)

    def fail_after_partial_write(stream, payload: bytes) -> None:
        stream.write(payload[:8])
        stream.flush()
        raise OSError("disk full")

    with patch(
        "solomon_harness.host_adapter_common._write_adapter_payload",
        side_effect=fail_after_partial_write,
    ), pytest.raises(OSError, match="disk full"):
        compile_project_adapters(tmp_path)

    assert _snapshot(tmp_path) == before
    assert not any(
        path.name.startswith(".agent.md.")
        or path.name.startswith(".local_specialist.md.")
        or path.name.startswith(".local_specialist.toml.")
        for path in tmp_path.rglob("*")
    )


@pytest.mark.unit
def test_compile_requires_a_valid_installed_manifest(tmp_path: Path) -> None:
    with pytest.raises(InstallConflictError, match="manifest"):
        compile_project_adapters(tmp_path)

    manifest = HarnessPaths(tmp_path).manifest
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("not json\n", encoding="utf-8")
    with pytest.raises(InstallConflictError, match="manifest"):
        compile_project_adapters(tmp_path)


@pytest.mark.integration
def test_generated_adapter_modes_and_manifest_are_independent_of_umask(
    tmp_path: Path,
) -> None:
    manifests: list[dict[str, dict[str, object]]] = []
    for name, mask in (("open", 0o000), ("private", 0o077)):
        root = tmp_path / name
        previous = os.umask(mask)
        try:
            install_project(root, source_root=SOURCE_ROOT)
        finally:
            os.umask(previous)
        manifests.append(
            {
                relative: entry
                for relative, entry in _manifest_entries(root).items()
                if entry["owner"] == "adapter"
            }
        )
        for relative in (
            ".agents/agents/qa/agent.md",
            ".claude/agents/qa.md",
            ".codex/agents/qa.toml",
        ):
            assert stat.S_IMODE((root / relative).stat().st_mode) == 0o644

    assert manifests[0] == manifests[1]
