"""Contracts for the repository's Python test and coverage infrastructure."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from solomon_harness.install_layout import _atomic_write


ROOT = Path(__file__).resolve().parents[1]
_PHYSICAL_FSYNC = os.fsync
_PHYSICAL_REPLACE = os.replace


@pytest.mark.unit
def test_dev_group_installs_pytest_cov() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = configuration["dependency-groups"]["dev"]

    assert any(dependency.startswith("pytest-cov") for dependency in dependencies)


@pytest.mark.unit
def test_pytest_registers_quality_markers() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    markers = configuration["tool"]["pytest"]["ini_options"]["markers"]

    assert any(marker.startswith("unit:") for marker in markers)
    assert any(marker.startswith("integration:") for marker in markers)
    assert any(marker.startswith("e2e:") for marker in markers)
    assert any(marker.startswith("real_fsync:") for marker in markers)


@pytest.mark.unit
def test_ci_enforces_package_branch_coverage_floor() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--cov=solomon_harness" in workflow
    assert "--cov-branch" in workflow
    assert "--cov-report=term-missing" in workflow
    assert "--cov-fail-under=80" in workflow


@pytest.mark.unit
def test_ci_enforces_host_neutral_core_coverage_floor() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Enforce host-neutral core branch coverage" in workflow
    for module in (
        "host_adapter_agy.py",
        "host_adapter_claude.py",
        "host_adapter_codex.py",
        "host_adapter_contract.py",
        "host_adapters.py",
        "payload_inventory.py",
    ):
        assert module in workflow
    assert "--fail-under=90" in workflow


@pytest.mark.unit
def test_default_test_fixture_replaces_only_physical_fsync() -> None:
    assert os.fsync is not _PHYSICAL_FSYNC
    assert os.replace is _PHYSICAL_REPLACE


@pytest.mark.integration
@pytest.mark.real_fsync
def test_atomic_write_flushes_before_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    def observed_fsync(descriptor: int) -> None:
        events.append("fsync")
        _PHYSICAL_FSYNC(descriptor)

    def observed_replace(source: str | bytes | Path, target: str | bytes | Path) -> None:
        events.append("replace")
        _PHYSICAL_REPLACE(source, target)

    monkeypatch.setattr(os, "fsync", observed_fsync)
    monkeypatch.setattr(os, "replace", observed_replace)

    target = tmp_path / "atomic.txt"
    assert _atomic_write(target, b"durable\n", 0o644) is True

    assert events == ["fsync", "replace"]
    assert target.read_bytes() == b"durable\n"
