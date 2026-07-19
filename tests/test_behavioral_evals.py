"""Contract tests for the offline behavioral-evaluation core (#369)."""

import copy
import json
import os
import shutil
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from solomon_harness import behavioral_evals, secure_paths
from solomon_harness.behavioral_evals import (
    EvaluationError,
    canonical_json,
    load_manifest,
    prepare_pilot,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def _manifest_data() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _invalid_manifest_data(variant: str) -> dict[str, Any]:
    data = copy.deepcopy(_manifest_data())
    if variant == "unsupported_schema":
        data["schema_version"] = 2
    elif variant == "wrong_repetitions":
        data["repetitions"] = 2
    elif variant == "wrong_arms":
        data["arms"] = data["arms"][:1]
    elif variant == "too_few_cases":
        data["cases"] = data["cases"][:8]
    elif variant == "duplicate_case":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    elif variant == "bool_budget":
        data["budget"]["max_files"] = True
    elif variant == "budget_above_hard_cap":
        data["budget"]["max_files"] = 1000000
    elif variant == "unsafe_fixture_path":
        data["cases"][0]["fixture_path"] = "../outside"
    elif variant == "unsafe_assertion_path":
        data["cases"][0]["assertions"]["required_files"] = [r"C:\outside.txt"]
    elif variant == "prompt_above_budget":
        data["budget"]["max_prompt_bytes"] = 1
    elif variant == "unknown_root_field":
        data["surprise"] = "ignored"
    elif variant == "unknown_nested_field":
        data["cases"][0]["assertions"]["surprise"] = "ignored"
    elif variant == "unknown_budget_field":
        data["budget"]["surprise"] = 1
    elif variant == "unknown_policy_field":
        data["arms"][0]["policy"]["surprise"] = False
    elif variant == "unknown_case_field":
        data["cases"][0]["surprise"] = "ignored"
    else:
        raise AssertionError(f"unknown test variant: {variant}")
    return data


def _write_manifest(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_manifest_loads_closed_versioned_contract() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert manifest.schema_version == 1
    assert manifest.golden_set_version == "2026-07-18.1"
    assert tuple(arm.arm_id for arm in manifest.arms) == ("baseline", "candidate")
    assert manifest.repetitions == 3
    assert len(manifest.cases) == 9
    assert {case.case_id for case in manifest.cases} == {
        f"{role}-{path}"
        for role in ("planning", "implementation", "review")
        for path in ("happy", "boundary", "failure")
    }
    assert canonical_json({"z": 1, "nested": {"b": 2, "a": 3}}) == (
        '{"nested":{"a":3,"b":2},"z":1}'
    )
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, "repetitions", 4)


@pytest.mark.parametrize(
    ("variant", "error_code"),
    [
        ("unsupported_schema", "unsupported_schema"),
        ("wrong_repetitions", "invalid_manifest"),
        ("wrong_arms", "invalid_manifest"),
        ("too_few_cases", "invalid_manifest"),
        ("duplicate_case", "invalid_manifest"),
        ("bool_budget", "invalid_manifest"),
        ("budget_above_hard_cap", "limit_exceeded"),
        ("unsafe_fixture_path", "unsafe_path"),
        ("unsafe_assertion_path", "unsafe_path"),
        ("prompt_above_budget", "limit_exceeded"),
        ("unknown_root_field", "invalid_manifest"),
        ("unknown_nested_field", "invalid_manifest"),
        ("unknown_budget_field", "invalid_manifest"),
        ("unknown_policy_field", "invalid_manifest"),
        ("unknown_case_field", "invalid_manifest"),
    ],
)
def test_manifest_rejects_invalid_bounds_and_unsafe_fixture_paths(
    tmp_path: Path,
    variant: str,
    error_code: str,
) -> None:
    path = _write_manifest(tmp_path, _invalid_manifest_data(variant))

    with pytest.raises(EvaluationError) as raised:
        load_manifest(path)

    assert raised.value.code == error_code
    assert str(tmp_path) not in str(raised.value)


@pytest.mark.parametrize("invalid_token", ["duplicate", "NaN", "Infinity"])
def test_manifest_rejects_ambiguous_or_non_finite_json(
    tmp_path: Path,
    invalid_token: str,
) -> None:
    raw = MANIFEST_PATH.read_text(encoding="utf-8")
    if invalid_token == "duplicate":
        raw = raw.replace(
            '"schema_version": 1,',
            '"schema_version": 1, "schema_version": 1,',
            1,
        )
    else:
        raw = raw.replace('"max_duration_ms": 600000', f'"max_duration_ms": {invalid_token}', 1)
    path = tmp_path / "manifest.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(EvaluationError) as raised:
        load_manifest(path)

    assert raised.value.code == "invalid_manifest"


def test_manifest_rejects_symlinked_or_oversized_input(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(MANIFEST_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    symlink = tmp_path / "manifest.json"
    symlink.symlink_to(target)

    with pytest.raises(EvaluationError) as symlink_error:
        load_manifest(symlink)
    assert symlink_error.value.code == "unsafe_path"

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 1_000_001)
    with pytest.raises(EvaluationError) as size_error:
        load_manifest(oversized)
    assert size_error.value.code == "limit_exceeded"


def test_prepare_pilot_creates_54_fresh_bounded_scratch_fixtures(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)

    first = prepare_pilot(manifest, tmp_path)

    expected_ids = {
        (case.case_id, arm.arm_id, repetition)
        for case in manifest.cases
        for arm in manifest.arms
        for repetition in range(1, 4)
    }
    assert len(first) == 54
    assert {(run.case_id, run.arm_id, run.repetition) for run in first} == expected_ids
    assert len({run.scratch_path for run in first}) == 54
    assert all(stat.S_IMODE(run.scratch_path.stat().st_mode) == 0o700 for run in first)
    assert all((run.workspace_path / "task.txt").is_file() for run in first)
    assert all(stat.S_IMODE(run.request_path.stat().st_mode) == 0o600 for run in first)
    assert all(
        stat.S_IMODE(run.workspace_path.joinpath("task.txt").stat().st_mode) == 0o600
        for run in first
    )
    request = json.loads(first[0].request_path.read_text(encoding="utf-8"))
    assert request["case"]["prompt"] == manifest.cases[0].prompt
    assert request["artifact_contract"] == {
        "required_files": ["PLAN.md"],
        "expected_exit_code": 0,
    }
    assert "forbidden_actions" not in canonical_json(request)
    assert "protected_state" not in canonical_json(request)

    first[0].workspace_path.joinpath("task.txt").write_text("mutated", encoding="utf-8")
    second = prepare_pilot(manifest, tmp_path)

    assert {run.scratch_path for run in first}.isdisjoint(
        {run.scratch_path for run in second}
    )
    assert second[0].workspace_path.joinpath("task.txt").read_text(encoding="utf-8") != "mutated"


def test_prepare_rejects_symlinked_seed_or_scratch_root(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    external = tmp_path / "external.txt"
    external.write_text("do not copy", encoding="utf-8")
    seed = fixture_copy / "cases" / "planning-happy" / "task.txt"
    seed.unlink()
    seed.symlink_to(external)
    manifest = load_manifest(fixture_copy / "manifest.json")

    with pytest.raises(EvaluationError) as seed_error:
        prepare_pilot(manifest, tmp_path / "safe-scratch")
    assert seed_error.value.code == "unsafe_path"

    real_scratch = tmp_path / "real-scratch"
    real_scratch.mkdir()
    linked_scratch = tmp_path / "linked-scratch"
    linked_scratch.symlink_to(real_scratch, target_is_directory=True)
    with pytest.raises(EvaluationError) as root_error:
        prepare_pilot(load_manifest(MANIFEST_PATH), linked_scratch)
    assert root_error.value.code == "unsafe_path"


def test_prepare_never_reuses_a_preexisting_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(behavioral_evals.secrets, "token_hex", lambda _size: "fixed")
    manifest = load_manifest(MANIFEST_PATH)
    first = prepare_pilot(manifest, tmp_path)
    sentinel = first[0].workspace_path / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(EvaluationError) as raised:
        prepare_pilot(manifest, tmp_path)

    assert raised.value.code == "unsafe_path"
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert stat.S_IMODE(os.stat(tmp_path / "behavioral-eval-fixed").st_mode) == 0o700


def test_prepare_rejects_special_hardlinked_or_raced_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    seed = fixture_copy / "cases" / "planning-happy" / "task.txt"
    seed.unlink()
    os.mkfifo(seed)
    with pytest.raises(EvaluationError) as special_error:
        prepare_pilot(load_manifest(fixture_copy / "manifest.json"), tmp_path / "special")
    assert special_error.value.code == "unsafe_path"

    seed.unlink()
    external = tmp_path / "external.txt"
    external.write_text("external", encoding="utf-8")
    os.link(external, seed)
    with pytest.raises(EvaluationError) as link_error:
        prepare_pilot(load_manifest(fixture_copy / "manifest.json"), tmp_path / "hardlink")
    assert link_error.value.code == "unsafe_path"

    seed.unlink()
    seed.write_text("original", encoding="utf-8")
    real_open = secure_paths.os.open
    swapped = False

    def swap_before_open(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if (
            path == "task.txt"
            and dir_fd is not None
            and flags & os.O_NOFOLLOW
            and not flags & (os.O_WRONLY | os.O_CREAT)
            and not swapped
        ):
            swapped = True
            os.rename(
                "task.txt",
                "task-original.txt",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(external, "task.txt", dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(secure_paths.os, "open", swap_before_open)
    with pytest.raises(EvaluationError) as race_error:
        prepare_pilot(load_manifest(fixture_copy / "manifest.json"), tmp_path / "race")
    assert race_error.value.code == "unsafe_path"
    assert external.read_text(encoding="utf-8") == "external"
