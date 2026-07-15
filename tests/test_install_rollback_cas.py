from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from solomon_harness.install_layout import (
    InstallConflictError,
    _RollbackSnapshot,
    install_project,
    load_manifest,
    uninstall_project,
)
from solomon_harness.install_transaction import (
    observe_install_mutations,
    record_install_mutation,
)
from solomon_harness.layout import HarnessPaths


SOURCE_ROOT = Path(__file__).resolve().parents[1]
NO_ADAPTER_CHANGES = SimpleNamespace(changed=False, conflicts=(), managed_paths=())


def _repository_entries(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


@pytest.mark.integration
def test_failed_install_preserves_concurrent_core_edit(tmp_path: Path) -> None:
    core = HarnessPaths(tmp_path).python_package / "cli.py"

    def edit_core_then_fail(_: Path) -> None:
        core.write_text("external edit\n", encoding="utf-8")
        raise RuntimeError("renderer failed after external edit")

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=edit_core_then_fail,
    ):
        with pytest.raises(InstallConflictError, match=r"solomon_harness/cli\.py"):
            install_project(tmp_path, source_root=SOURCE_ROOT)

    assert core.read_text(encoding="utf-8") == "external edit\n"
    assert not HarnessPaths(tmp_path).manifest.exists()


@pytest.mark.integration
def test_failed_install_preserves_adapter_edit_after_recorded_partial_write(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / ".claude" / "agents" / "qa.md"

    def render_then_external_edit(_: Path) -> None:
        adapter.parent.mkdir(parents=True, exist_ok=True)
        adapter.write_text("transaction output\n", encoding="utf-8")
        record_install_mutation(adapter)
        adapter.write_text("external adapter edit\n", encoding="utf-8")
        raise RuntimeError("renderer failed after adapter edit")

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=render_then_external_edit,
    ):
        with pytest.raises(InstallConflictError, match=r"\.claude/agents/qa\.md"):
            install_project(tmp_path, source_root=SOURCE_ROOT)

    assert adapter.read_text(encoding="utf-8") == "external adapter edit\n"


@pytest.mark.unit
def test_rollback_restores_unchanged_transaction_write(tmp_path: Path) -> None:
    target = tmp_path / "managed.txt"
    target.write_text("before\n", encoding="utf-8")
    snapshot = _RollbackSnapshot(tmp_path, (target,))

    with observe_install_mutations(snapshot.checkpoint):
        target.write_text("transaction\n", encoding="utf-8")
        record_install_mutation(target)

    assert snapshot.rollback() == ()
    assert target.read_text(encoding="utf-8") == "before\n"


@pytest.mark.unit
def test_rollback_preserves_file_recreated_after_transaction_removal(
    tmp_path: Path,
) -> None:
    target = tmp_path / "managed.txt"
    target.write_text("before\n", encoding="utf-8")
    snapshot = _RollbackSnapshot(tmp_path, (target,))

    with observe_install_mutations(snapshot.checkpoint):
        target.unlink()
        record_install_mutation(target)
        target.write_text("external recreation\n", encoding="utf-8")

    assert snapshot.rollback() == ("managed.txt",)
    assert target.read_text(encoding="utf-8") == "external recreation\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory metadata contract")
@pytest.mark.unit
def test_rollback_restores_recorded_parent_directory_mode_and_mtime(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    target = parent / "managed.txt"
    target.write_text("before\n", encoding="utf-8")
    original_mtime = 1_700_000_000_123_456_789
    os.utime(parent, ns=(original_mtime, original_mtime))
    snapshot = _RollbackSnapshot(tmp_path, (target,))

    with observe_install_mutations(snapshot.checkpoint):
        os.chmod(parent, 0o755)
        record_install_mutation(parent)

    assert snapshot.rollback() == ()
    info = parent.stat()
    assert stat.S_IMODE(info.st_mode) == 0o700
    assert info.st_mtime_ns == original_mtime


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory metadata contract")
@pytest.mark.unit
def test_rollback_preserves_concurrent_parent_directory_metadata_change(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    target = parent / "managed.txt"
    target.write_text("before\n", encoding="utf-8")
    snapshot = _RollbackSnapshot(tmp_path, (target,))

    with observe_install_mutations(snapshot.checkpoint):
        os.chmod(parent, 0o755)
        record_install_mutation(parent)
        concurrent_mtime = 1_710_000_000_987_654_321
        os.chmod(parent, 0o711)
        os.utime(parent, ns=(concurrent_mtime, concurrent_mtime))

    assert snapshot.rollback() == ("private",)
    info = parent.stat()
    assert stat.S_IMODE(info.st_mode) == 0o711
    assert info.st_mtime_ns == concurrent_mtime


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory metadata contract")
@pytest.mark.integration
def test_failed_legacy_migration_restores_directory_modes_and_mtimes(
    tmp_path: Path,
) -> None:
    decision = tmp_path / ".solomon" / "memory-mirror" / "decision"
    decision.mkdir(parents=True)
    (decision / "one.md").write_text("legacy\n", encoding="utf-8")
    directories = (tmp_path / ".solomon", decision.parent, decision)
    expected: dict[Path, tuple[int, int]] = {}
    for index, (directory, mode) in enumerate(
        zip(directories, (0o700, 0o710, 0o711), strict=True)
    ):
        timestamp = 1_700_000_000_000_000_000 + index * 10_000
        os.chmod(directory, mode)
        os.utime(directory, ns=(timestamp, timestamp))
        expected[directory] = (mode, timestamp)

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=RuntimeError("renderer failed after migration"),
    ):
        with pytest.raises(RuntimeError, match="renderer failed after migration"):
            install_project(tmp_path, source_root=SOURCE_ROOT)

    for directory, (mode, mtime_ns) in expected.items():
        info = directory.stat()
        assert stat.S_IMODE(info.st_mode) == mode
        assert info.st_mtime_ns == mtime_ns


@pytest.mark.integration
def test_failed_fresh_install_leaves_an_empty_workspace(tmp_path: Path) -> None:
    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=RuntimeError("renderer failed"),
    ):
        with pytest.raises(RuntimeError, match="renderer failed"):
            install_project(tmp_path, source_root=SOURCE_ROOT)

    assert _repository_entries(tmp_path) == ()


@pytest.mark.integration
def test_invalid_install_source_leaves_an_empty_workspace(tmp_path: Path) -> None:
    with pytest.raises(InstallConflictError, match="payload is unavailable"):
        install_project(tmp_path, source_root=tmp_path / "missing-source")

    assert _repository_entries(tmp_path) == ()


@pytest.mark.unit
def test_uninstall_in_never_installed_workspace_is_a_true_noop(tmp_path: Path) -> None:
    result = uninstall_project(tmp_path)

    assert result.changed is False
    assert _repository_entries(tmp_path) == ()


@pytest.mark.integration
def test_uninstalled_adapter_compile_does_not_materialize_repository_state(
    tmp_path: Path,
) -> None:
    from solomon_harness.host_adapters import compile_adapters

    with pytest.raises(FileNotFoundError):
        compile_adapters(tmp_path)

    assert _repository_entries(tmp_path) == ()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
@pytest.mark.integration
def test_fresh_install_under_open_umask_secures_every_managed_parent(
    tmp_path: Path,
) -> None:
    previous_umask = os.umask(0)
    try:
        install_project(tmp_path, source_root=SOURCE_ROOT)
    finally:
        os.umask(previous_umask)

    manifest = load_manifest(tmp_path)
    parents: set[Path] = set()
    for entry in manifest["entries"]:
        current = (tmp_path / entry["path"]).parent
        while current != tmp_path:
            parents.add(current)
            current = current.parent
    state = HarnessPaths(tmp_path).state
    parents.update(path for path in state.rglob("*") if path.is_dir())
    parents.add(state)

    assert parents
    for directory in parents:
        mode = stat.S_IMODE(directory.stat().st_mode)
        assert mode & 0o022 == 0, directory.relative_to(tmp_path).as_posix()
        if directory == state or state in directory.parents:
            assert mode == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
@pytest.mark.integration
def test_install_does_not_silently_chmod_unsafe_existing_tenant_directory(
    tmp_path: Path,
) -> None:
    tenant = tmp_path / ".claude"
    tenant.mkdir(mode=0o777)
    os.chmod(tenant, 0o777)

    with pytest.raises((InstallConflictError, ValueError), match="directory|writable|mode"):
        install_project(tmp_path, source_root=SOURCE_ROOT)

    assert stat.S_IMODE(tenant.stat().st_mode) == 0o777


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
@pytest.mark.parametrize(
    "relative",
    (
        ".agents/solomon/config",
        ".agents/solomon/solomon_harness",
        ".claude",
    ),
)
@pytest.mark.integration
def test_reinstall_rejects_unsafe_managed_parent_without_chmod(
    tmp_path: Path,
    relative: str,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    directory = tmp_path / relative
    os.chmod(directory, 0o777)

    with pytest.raises((InstallConflictError, ValueError), match="writable mode"):
        install_project(tmp_path, source_root=SOURCE_ROOT)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o777


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
@pytest.mark.parametrize("relative", ("docs", ".github"))
@pytest.mark.integration
def test_install_preserves_existing_group_writable_project_parent(
    tmp_path: Path,
    relative: str,
) -> None:
    directory = tmp_path / relative
    directory.mkdir(mode=0o775)
    os.chmod(directory, 0o775)
    unrelated = directory / "consumer.md"
    unrelated.write_text("consumer\n", encoding="utf-8")

    install_project(tmp_path, source_root=SOURCE_ROOT)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o775
    assert unrelated.read_text(encoding="utf-8") == "consumer\n"


@pytest.mark.integration
def test_failed_install_reports_external_file_in_new_adapter_directory(
    tmp_path: Path,
) -> None:
    external = tmp_path / ".claude" / "agents" / "external.md"

    def create_external_file_then_fail(_: Path) -> None:
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_text("external\n", encoding="utf-8")
        raise RuntimeError("renderer failed after external directory write")

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        side_effect=create_external_file_then_fail,
    ):
        with pytest.raises(InstallConflictError, match=r"\.claude/agents"):
            install_project(tmp_path, source_root=SOURCE_ROOT)

    assert external.read_text(encoding="utf-8") == "external\n"


@pytest.mark.integration
def test_install_classifies_core_and_adapter_conflicts_as_blocking(
    tmp_path: Path,
) -> None:
    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        return_value=NO_ADAPTER_CHANGES,
    ):
        install_project(tmp_path, source_root=SOURCE_ROOT)

    core = HarnessPaths(tmp_path).python_package / "cli.py"
    core.write_text("consumer core edit\n", encoding="utf-8")
    adapter_conflict = ".claude/agents/qa.md"
    adapter_result = SimpleNamespace(
        changed=False,
        conflicts=(adapter_conflict,),
        managed_paths=(),
    )
    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        return_value=adapter_result,
    ):
        result = install_project(tmp_path, source_root=SOURCE_ROOT)

    core_relative = core.relative_to(tmp_path).as_posix()
    assert {core_relative, adapter_conflict} <= set(result.blocking_conflicts)
    assert set(result.blocking_conflicts) <= set(result.conflicts)


@pytest.mark.integration
def test_install_blocks_invalid_canonical_config_type(tmp_path: Path) -> None:
    config = HarnessPaths(tmp_path).config
    config.mkdir(parents=True)

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        return_value=NO_ADAPTER_CHANGES,
    ):
        result = install_project(tmp_path, source_root=SOURCE_ROOT)

    relative = config.relative_to(tmp_path).as_posix()
    assert relative in result.conflicts
    assert relative in result.blocking_conflicts


@pytest.mark.integration
def test_install_keeps_legacy_warning_nonblocking_but_blocks_sqlite_conflict(
    tmp_path: Path,
) -> None:
    paths = HarnessPaths(tmp_path)
    paths.legacy_config.parent.mkdir(parents=True)
    paths.legacy_config.write_text('{"legacy": true}\n', encoding="utf-8")
    paths.config.parent.mkdir(parents=True)
    paths.config.write_text('{"canonical": true}\n', encoding="utf-8")
    for database, value in (
        (paths.legacy_sqlite_database, "legacy"),
        (paths.sqlite_database, "canonical"),
    ):
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE probe (value TEXT NOT NULL)")
            connection.execute("INSERT INTO probe (value) VALUES (?)", (value,))

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        return_value=NO_ADAPTER_CHANGES,
    ):
        result = install_project(tmp_path, source_root=SOURCE_ROOT)

    legacy_config = paths.legacy_config.relative_to(tmp_path).as_posix()
    legacy_database = paths.legacy_sqlite_database.relative_to(tmp_path).as_posix()
    assert {legacy_config, legacy_database} <= set(result.conflicts)
    assert legacy_config not in result.blocking_conflicts
    assert legacy_database in result.blocking_conflicts
