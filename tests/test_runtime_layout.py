"""Runtime path contracts for the host-neutral installed harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from solomon_harness import capability_router, healthcheck, memory, notify
from solomon_harness.agent_selection import discover_agents, select_agents
from solomon_harness.bootstrap import ensure_database_config
from solomon_harness.layout import HarnessPaths, PathConfinementError, confined_path
from solomon_harness.loop_policy import LoopPolicy, clear_stop, write_stop
from solomon_harness.memory_service import resolve_harness_dir
from solomon_harness.tools.database_client import DatabaseClient


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_agent(agents_dir: Path, name: str, description: str = "Role summary.") -> None:
    role = agents_dir / name / "agents" / f"{name}.md"
    role.parent.mkdir(parents=True, exist_ok=True)
    role.write_text(f"# {name}\n\n{description}\n", encoding="utf-8")


def _write_pending_mirror(state_dir: Path, name: str = "one") -> None:
    mirror = state_dir / "memory-mirror" / "decision" / f"{name}.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(
        "---\n"
        f"id: {name}\n"
        "kind: decision\n"
        "created_at: 2026-07-15T00:00:00+00:00\n"
        "synced: false\n"
        "---\n",
        encoding="utf-8",
    )


def test_confined_path_rejects_an_intermediate_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / "solomon").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathConfinementError):
        confined_path(tmp_path, ".agents/solomon/config/project.json")

    assert not (outside / "config" / "project.json").exists()


def test_mutable_handoffs_live_below_state_with_legacy_read_fallback(
    tmp_path: Path,
) -> None:
    paths = HarnessPaths(tmp_path)
    assert paths.handoffs == paths.state / "handoffs"

    old_canonical = paths.solomon / "handoffs"
    old_canonical.mkdir(parents=True)
    assert paths.resolve_handoffs() == old_canonical

    paths.handoffs.mkdir(parents=True)
    assert paths.resolve_handoffs() == paths.handoffs


def test_database_config_write_rejects_a_canonical_parent_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-config-outside"
    outside.mkdir()
    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / "solomon").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathConfinementError):
        ensure_database_config(str(tmp_path))

    assert not (outside / "config" / "project.json").exists()


def test_database_config_preserves_malformed_json_byte_for_byte(
    tmp_path: Path,
) -> None:
    paths = HarnessPaths(tmp_path)
    malformed = b'{"database": '
    paths.config.parent.mkdir(parents=True)
    paths.config.write_bytes(malformed)

    with pytest.raises(ValueError, match="valid JSON object"):
        ensure_database_config(str(tmp_path))

    assert paths.config.read_bytes() == malformed


def test_config_readers_prefer_canonical_project_config(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_json(
        paths.legacy_config,
        {
            "database": {"provider": "legacy", "url": "ws://legacy:9000/rpc"},
            "loop": {"autonomy": "L1"},
            "notify": {"enabled": False},
        },
    )
    _write_json(
        paths.config,
        {
            "database": {"provider": "canonical", "url": "ws://canonical:9001/rpc"},
            "loop": {"autonomy": "L2"},
            "notify": {"mode": "console"},
        },
    )

    assert memory._read_db_url(str(tmp_path)) == (
        "canonical",
        "ws://canonical:9001/rpc",
    )
    assert healthcheck._db_config(str(tmp_path))["provider"] == "canonical"
    assert LoopPolicy.from_config(str(tmp_path), env={}).level == "L2"
    assert isinstance(notify.get_notifier(str(tmp_path), env={}), notify.ConsoleNotifier)


def test_config_readers_fall_back_to_legacy_config(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_json(
        paths.legacy_config,
        {
            "database": {"provider": "sqlite", "url": "ws://legacy:9000/rpc"},
            "loop": {"autonomy": "L1"},
            "notify": {"mode": "console"},
        },
    )

    assert memory._read_db_url(str(tmp_path)) == ("sqlite", "ws://legacy:9000/rpc")
    assert healthcheck._db_config(str(tmp_path))["provider"] == "sqlite"
    assert LoopPolicy.from_config(str(tmp_path), env={}).level == "L1"
    assert isinstance(notify.get_notifier(str(tmp_path), env={}), notify.ConsoleNotifier)


def test_database_client_writes_default_state_only_below_canonical_home(
    tmp_path: Path,
) -> None:
    paths = HarnessPaths(tmp_path)
    (tmp_path / ".git").mkdir()
    _write_json(
        paths.config,
        {"database": {"provider": "sqlite", "busy_timeout_seconds": 0.25}},
    )
    _write_json(
        paths.legacy_config,
        {"database": {"provider": "sqlite", "busy_timeout_seconds": 9.0}},
    )

    with DatabaseClient(harness_dir=str(tmp_path)) as client:
        client.log_decision("Layout", "one home", "accepted", "qa", "main", "")
        assert Path(client.db_path or "") == paths.state / "memory" / "long_term" / "harness.db"
        assert Path(client._mirror_root) == paths.state / "memory-mirror"
        assert client.busy_timeout_seconds == 0.25

    assert not (tmp_path / "memory").exists()
    assert not paths.legacy_state.exists()


def test_healthcheck_reads_canonical_mirror_then_legacy_fallback(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_pending_mirror(paths.state, "canonical")
    _write_pending_mirror(paths.legacy_state, "legacy")

    assert healthcheck.pending_reconcile_count(str(tmp_path)) == 1

    canonical_mirror = paths.state / "memory-mirror"
    for file_path in sorted(canonical_mirror.rglob("*"), reverse=True):
        if file_path.is_file():
            file_path.unlink()
        else:
            file_path.rmdir()
    canonical_mirror.rmdir()
    paths.state.rmdir()

    assert healthcheck.pending_reconcile_count(str(tmp_path)) == 1


def test_memory_service_resolves_consumer_root_from_installed_package(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    package = paths.python_package / "tools"
    package.mkdir(parents=True)

    assert resolve_harness_dir(str(package)) == str(tmp_path.resolve())


def test_agent_discovery_and_catalog_prefer_canonical_agents(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_agent(paths.agents, "qa", "Canonical QA role.")
    _write_agent(paths.legacy_agents, "security", "Legacy security role.")

    assert discover_agents(str(tmp_path)) == {"qa"}
    catalog = capability_router.load_catalog(str(tmp_path))
    assert [(agent.name, agent.description) for agent in catalog] == [
        ("qa", "Canonical QA role."),
    ]


def test_agent_discovery_falls_back_to_legacy_agents(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_agent(paths.legacy_agents, "security", "Legacy security role.")

    assert discover_agents(str(tmp_path)) == {"security"}
    assert [agent.name for agent in capability_router.load_catalog(str(tmp_path))] == [
        "security"
    ]


def test_stack_detection_ignores_the_canonical_harness_payload(tmp_path: Path) -> None:
    paths = HarnessPaths(tmp_path)
    _write_agent(paths.agents, "qa")
    _write_agent(paths.agents, "flutter")
    harness_source = paths.solomon / "fixtures" / "main.dart"
    harness_source.parent.mkdir(parents=True)
    harness_source.write_text("void main() {}\n", encoding="utf-8")

    assert select_agents(str(tmp_path)) == ["qa"]


def test_non_git_kill_switch_writes_canonical_state_and_reads_legacy(
    tmp_path: Path,
) -> None:
    paths = HarnessPaths(tmp_path)

    written = Path(write_stop(str(tmp_path)))
    assert written == paths.state / "loop.stop"
    assert not (paths.legacy_state / "loop.stop").exists()
    assert clear_stop(str(tmp_path))

    legacy = paths.legacy_state / "loop.stop"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("halted\n", encoding="utf-8")
    assert LoopPolicy(str(tmp_path)).is_halted()
    assert clear_stop(str(tmp_path))
    assert not legacy.exists()


def test_git_kill_switch_remains_in_git_common_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    written = Path(write_stop(str(tmp_path)))

    assert written == tmp_path / ".git" / "solomon-loop.stop"
    assert clear_stop(str(tmp_path))
