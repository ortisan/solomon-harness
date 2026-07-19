"""Contract tests for the offline behavioral-evaluation core (#369)."""

import ast
import copy
import hashlib
import json
import os
import shutil
import stat
import statistics
import time
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from solomon_harness import behavioral_evals, secure_paths
from solomon_harness.behavioral_evals import (
    EvaluationError,
    GoldenCaseRegression,
    IncompleteComparisonError,
    canonical_json,
    compare_recordings,
    load_manifest,
    load_recordings,
    main,
    prepare_pilot,
    score_recordings,
    validate_complete_comparison,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RECORDINGS_PATH = FIXTURE_ROOT / "recorded-runs.json"


def _manifest_data() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _invalid_manifest_data(variant: str) -> dict[str, Any]:
    data = copy.deepcopy(_manifest_data())
    if variant == "unsupported_schema":
        data["schema_version"] += 1
    elif variant == "wrong_repetitions":
        data["repetitions"] = 2
    elif variant == "wrong_arms":
        data["arms"] = data["arms"][:1]
    elif variant == "wrong_arm_ids":
        data["arms"].reverse()
    elif variant == "too_few_cases":
        data["cases"] = data["cases"][:8]
    elif variant == "duplicate_case":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    elif variant == "bool_budget":
        data["budget"]["max_files"] = True
    elif variant == "file_budget_above_total":
        data["budget"]["max_file_bytes"] = data["budget"]["max_total_bytes"] + 1
    elif variant == "budget_above_hard_cap":
        data["budget"]["max_files"] = 1000000
    elif variant == "unsafe_fixture_path":
        data["cases"][0]["fixture_path"] = "../outside"
    elif variant == "unsafe_assertion_path":
        data["cases"][0]["assertions"]["required_files"] = [r"C:\outside.txt"]
    elif variant == "deep_assertion_path":
        data["cases"][0]["assertions"]["required_files"] = ["/".join(["x"] * 17)]
    elif variant == "long_path_component":
        data["cases"][0]["assertions"]["required_files"] = ["x" * 129]
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
    elif variant == "non_boolean_network":
        data["arms"][0]["policy"]["network_allowed"] = 0
    elif variant == "duplicate_tool":
        data["arms"][0]["policy"]["tools"] = ["Read", "Read"]
    elif variant == "invalid_case_id":
        data["cases"][0]["id"] = "Planning-Happy"
    elif variant == "invalid_role":
        data["cases"][0]["role"] = "operator"
    elif variant == "missing_role_scenario_coverage":
        data["cases"][0]["id"] = "planning-other"
    elif variant == "boolean_schema":
        data["schema_version"] = True
    elif variant == "invalid_unicode_version":
        data["golden_set_version"] = "\ud800"
    elif variant == "long_golden_set_version":
        data["golden_set_version"] = "x" * 65
    else:
        raise AssertionError(f"unknown test variant: {variant}")
    return data


def _write_manifest(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _raw_run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "case_id": "planning-happy",
        "case_version": "1",
        "arm": "baseline",
        "repetition": 1,
        "agent_content": "baseline agent content\n",
        "effective_policy": {
            "tools": ["Read", "Glob", "Grep"],
            "network_allowed": False,
        },
        "host": {"name": "codex", "version": "1.2.3", "provider": "openai"},
        "model": {"name": "gpt-5", "version": "2026-07-01"},
        "effort": "medium",
        "duration_ms": 1200,
        "exit_code": 0,
        "files": ["PLAN.md"],
        "actions": ["read_contract"],
        "containment": {
            "scratch_only": True,
            "protected_state": [
                {
                    "resource": "source_checkout",
                    "before_digest": "sha256:" + "1" * 64,
                    "after_digest": "sha256:" + "1" * 64,
                },
                {
                    "resource": "project_memory",
                    "before_digest": "sha256:" + "2" * 64,
                    "after_digest": "sha256:" + "2" * 64,
                },
                {
                    "resource": "github",
                    "before_digest": "sha256:" + "3" * 64,
                    "after_digest": "sha256:" + "3" * 64,
                },
            ],
            "denied_actions": [],
        },
    }
    run.update(overrides)
    return run


def _usage_record(**overrides: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "case_id": "planning-happy",
        "arm": "baseline",
        "repetition": 1,
        "input_tokens": 321,
        "output_tokens": 45,
        "cache_tokens": None,
        "reported_cost_microusd": None,
    }
    usage.update(overrides)
    return usage


def _write_recordings(
    tmp_path: Path,
    runs: list[dict[str, Any]],
    usage_records: list[dict[str, Any]],
    **overrides: Any,
) -> Path:
    path = tmp_path / "recorded-runs.json"
    manifest = load_manifest(MANIFEST_PATH)
    assert manifest.golden_set_digest is not None
    document = {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "golden_set_digest": manifest.golden_set_digest,
        "runs": runs,
        "usage_records": usage_records,
    }
    document.update(overrides)
    path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )
    return path


def _passing_raw_run(
    manifest: Any,
    case_id: str,
    arm_id: str,
    repetition: int,
    duration_ms: int,
) -> dict[str, Any]:
    case = next(case for case in manifest.cases if case.case_id == case_id)
    arm = next(arm for arm in manifest.arms if arm.arm_id == arm_id)
    return _raw_run(
        case_id=case.case_id,
        case_version=case.version,
        arm=arm.arm_id,
        repetition=repetition,
        agent_content=f"{arm.arm_id} agent content\n",
        effective_policy=arm.policy.to_data(),
        duration_ms=duration_ms,
        exit_code=case.assertions.expected_exit_code,
        files=list(case.assertions.required_files),
        actions=list(case.assertions.required_actions),
    )


def _complete_raw_runs(manifest: Any) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for arm_index, arm in enumerate(manifest.arms):
        duration_ms = 1 + arm_index * 100
        for case in manifest.cases:
            for repetition in range(1, manifest.repetitions + 1):
                runs.append(
                    _passing_raw_run(
                        manifest,
                        case.case_id,
                        arm.arm_id,
                        repetition,
                        duration_ms,
                    )
                )
                duration_ms += 1
    return runs


def _usage_for_run(run: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    return _usage_record(
        case_id=run["case_id"],
        arm=run["arm"],
        repetition=run["repetition"],
        **overrides,
    )


def test_manifest_loads_closed_versioned_contract() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert manifest.schema_version == 2
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
    assert manifest.to_data() == _manifest_data()
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, "repetitions", 4)


@pytest.mark.parametrize(
    ("variant", "error_code"),
    [
        ("unsupported_schema", "unsupported_schema"),
        ("wrong_repetitions", "invalid_manifest"),
        ("wrong_arms", "invalid_manifest"),
        ("wrong_arm_ids", "invalid_manifest"),
        ("too_few_cases", "invalid_manifest"),
        ("duplicate_case", "invalid_manifest"),
        ("bool_budget", "invalid_manifest"),
        ("file_budget_above_total", "invalid_manifest"),
        ("budget_above_hard_cap", "limit_exceeded"),
        ("unsafe_fixture_path", "unsafe_path"),
        ("unsafe_assertion_path", "unsafe_path"),
        ("deep_assertion_path", "limit_exceeded"),
        ("long_path_component", "limit_exceeded"),
        ("prompt_above_budget", "limit_exceeded"),
        ("unknown_root_field", "invalid_manifest"),
        ("unknown_nested_field", "invalid_manifest"),
        ("unknown_budget_field", "invalid_manifest"),
        ("unknown_policy_field", "invalid_manifest"),
        ("unknown_case_field", "invalid_manifest"),
        ("non_boolean_network", "invalid_manifest"),
        ("duplicate_tool", "invalid_manifest"),
        ("invalid_case_id", "invalid_manifest"),
        ("invalid_role", "invalid_manifest"),
        ("missing_role_scenario_coverage", "invalid_manifest"),
        ("boolean_schema", "invalid_manifest"),
        ("invalid_unicode_version", "invalid_manifest"),
        ("long_golden_set_version", "limit_exceeded"),
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
        schema_version = _manifest_data()["schema_version"]
        raw = raw.replace(
            f'"schema_version": {schema_version},',
            f'"schema_version": {schema_version}, "schema_version": {schema_version},',
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


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        (b"\xff", "json.encoding"),
        (b"{", "json.syntax"),
        (b"]", "json.structure"),
    ],
)
def test_manifest_maps_malformed_bytes_to_closed_errors(
    tmp_path: Path,
    raw: bytes,
    field: str,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(raw)

    with pytest.raises(EvaluationError) as raised:
        load_manifest(path)

    assert raised.value.code == "invalid_manifest"
    assert raised.value.field == field


def test_manifest_rejects_missing_parent_without_exposing_path(tmp_path: Path) -> None:
    path = tmp_path / "missing-parent" / "manifest.json"

    with pytest.raises(EvaluationError) as raised:
        load_manifest(path)

    assert raised.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "manifest"}
    }
    assert str(tmp_path) not in canonical_json(raised.value.to_data())


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
    original_seed = first[0].workspace_path.joinpath("task.txt").read_bytes()
    request = json.loads(first[0].request_path.read_text(encoding="utf-8"))
    assert request["golden_set_digest"] == manifest.golden_set_digest
    assert request["case"]["prompt"] == manifest.cases[0].prompt
    assert request["artifact_contract"] == manifest.cases[0].assertions.to_data()
    assert {run.golden_set_digest for run in first} == {manifest.golden_set_digest}

    first[0].workspace_path.joinpath("task.txt").write_text("mutated", encoding="utf-8")
    second = prepare_pilot(manifest, tmp_path)

    assert {run.scratch_path for run in first}.isdisjoint(
        {run.scratch_path for run in second}
    )
    assert second[0].workspace_path.joinpath("task.txt").read_bytes() == original_seed


def test_manifest_and_prepare_reject_symlinked_seed_or_scratch_root(
    tmp_path: Path,
) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    external = tmp_path / "external.txt"
    external.write_text("do not copy", encoding="utf-8")
    seed = fixture_copy / "cases" / "planning-happy" / "task.txt"
    seed.unlink()
    seed.symlink_to(external)
    with pytest.raises(EvaluationError) as seed_error:
        load_manifest(fixture_copy / "manifest.json")
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


def test_prepare_copies_nested_seed_directories_into_every_matching_run(
    tmp_path: Path,
) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    nested = fixture_copy / "cases" / "planning-happy" / "nested" / "deeper"
    nested.mkdir(parents=True)
    nested.joinpath("context.txt").write_text("bounded context", encoding="utf-8")
    nested.joinpath("second.txt").write_text("second context", encoding="utf-8")
    manifest = load_manifest(fixture_copy / "manifest.json")

    prepared = prepare_pilot(manifest, tmp_path / "scratch")

    matching = [run for run in prepared if run.case_id == "planning-happy"]
    assert len(matching) == 6
    assert all(
        run.workspace_path.joinpath("nested/deeper/context.txt").read_text(
            encoding="utf-8"
        )
        == "bounded context"
        for run in matching
    )
    assert all(
        run.workspace_path.joinpath("nested/deeper/second.txt").read_text(
            encoding="utf-8"
        )
        == "second context"
        for run in matching
    )


@pytest.mark.parametrize(
    ("variant", "field"),
    [
        ("file_count", "fixture.files"),
        ("file_bytes", "fixture.file_bytes"),
        ("total_bytes", "fixture.total_bytes"),
    ],
)
def test_manifest_rejects_seed_budget_boundaries(
    tmp_path: Path,
    variant: str,
    field: str,
) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    data = _manifest_data()
    case_root = fixture_copy / "cases" / "planning-happy"
    if variant == "file_count":
        data["budget"]["max_files"] = 1
        case_root.joinpath("extra.txt").write_text("x", encoding="utf-8")
    elif variant == "file_bytes":
        data["budget"]["max_file_bytes"] = 1
    else:
        task_size = len(case_root.joinpath("task.txt").read_bytes())
        case_root.joinpath("extra.txt").write_bytes(b"x" * task_size)
        data["budget"]["max_file_bytes"] = task_size
        data["budget"]["max_total_bytes"] = task_size * 2 - 1
    scratch_root = tmp_path / "scratch"

    with pytest.raises(EvaluationError) as raised:
        load_manifest(_write_manifest(fixture_copy, data))

    assert raised.value.to_data() == {
        "error": {"code": "limit_exceeded", "field": field}
    }
    assert not scratch_root.exists()


def test_manifest_rejects_seed_tree_at_safe_path_depth_limit(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    cursor = fixture_copy / "cases" / "planning-happy"
    for index in range(behavioral_evals.MAX_PATH_DEPTH + 1):
        cursor = cursor / f"depth-{index}"
        cursor.mkdir()
    scratch_root = tmp_path / "scratch"

    with pytest.raises(EvaluationError) as raised:
        load_manifest(fixture_copy / "manifest.json")

    assert raised.value.to_data() == {
        "error": {"code": "limit_exceeded", "field": "fixture.entry"}
    }
    assert not scratch_root.exists()


def test_seed_scan_maps_directory_read_failure_to_closed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)

    def deny_scan(_directory_fd: int) -> object:
        raise PermissionError("denied")

    monkeypatch.setattr(behavioral_evals.os, "scandir", deny_scan)

    with pytest.raises(EvaluationError) as raised:
        behavioral_evals._collect_seed_files(0, manifest.budget)

    assert raised.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "fixture"}
    }


def test_directory_creation_helpers_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open_directory_at = behavioral_evals.open_directory_at
    monkeypatch.setattr(behavioral_evals, "open_directory_at", lambda _fd, _name: None)
    with pytest.raises(EvaluationError) as disappeared:
        behavioral_evals._open_existing_directory(0, "missing", "fixture.entry")
    assert disappeared.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "fixture.entry"}
    }

    monkeypatch.setattr(behavioral_evals, "open_directory_at", real_open_directory_at)
    monkeypatch.setattr(behavioral_evals, "stat_at", lambda _fd, _name: None)

    def deny_mkdir(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(behavioral_evals.os, "mkdir", deny_mkdir)
    with pytest.raises(EvaluationError) as denied:
        behavioral_evals._exclusive_directory(0, "new", "scratch.fixture")
    assert denied.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "scratch.fixture"}
    }

    with pytest.raises(EvaluationError) as invalid_name:
        behavioral_evals._open_scratch_root(Path("."))
    assert invalid_name.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "scratch_root"}
    }

    monkeypatch.undo()
    missing_parent = tmp_path / "missing-parent" / "scratch"
    with pytest.raises(EvaluationError) as missing:
        behavioral_evals._open_scratch_root(missing_parent)
    assert missing.value.to_data() == {
        "error": {"code": "unsafe_path", "field": "scratch_root"}
    }


def test_ac_eval_05_normalize_artifact_preserves_usage_and_marks_missing_metrics_unavailable(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(tmp_path, [_raw_run()], [_usage_record()])

    bundle = load_recordings(path, manifest)

    assert len(bundle.runs) == 1
    run = bundle.runs[0]
    expected_content_digest = "sha256:" + hashlib.sha256(
        b"baseline agent content\n"
    ).hexdigest()
    expected_policy_json = '{"network_allowed":false,"tools":["Read","Glob","Grep"]}'
    expected_policy_digest = "sha256:" + hashlib.sha256(
        expected_policy_json.encode("utf-8")
    ).hexdigest()
    assert run.agent_content_digest == expected_content_digest
    assert run.policy_digest == expected_policy_digest
    assert run.effective_policy.to_data() == {
        "tools": ["Read", "Glob", "Grep"],
        "network_allowed": False,
    }
    assert run.host.to_data() == {
        "name": "codex",
        "version": "1.2.3",
        "provider": "openai",
    }
    assert run.model.to_data() == {"name": "gpt-5", "version": "2026-07-01"}
    assert run.effort == "medium"
    assert run.duration_ms == 1200
    assert bundle.usage_records[0].metrics.to_data() == {
        "input_tokens": 321,
        "output_tokens": 45,
        "cache_tokens": None,
        "reported_cost_microusd": None,
    }
    normalized = canonical_json(bundle.to_data())
    assert "baseline agent content" not in normalized
    assert '"cache_tokens":null' in normalized
    assert '"reported_cost_microusd":null' in normalized

    result = score_recordings(manifest, bundle)[0]
    assert result.to_data() == {
        "schema_version": manifest.schema_version,
        "golden_set_version": "2026-07-18.1",
        "golden_set_digest": manifest.golden_set_digest,
        "case_id": "planning-happy",
        "case_version": "1",
        "arm": "baseline",
        "repetition": 1,
        "agent_content_digest": expected_content_digest,
        "effective_policy": {
            "tools": ["Read", "Glob", "Grep"],
            "network_allowed": False,
        },
        "policy_digest": expected_policy_digest,
        "host": {"name": "codex", "version": "1.2.3", "provider": "openai"},
        "model": {"name": "gpt-5", "version": "2026-07-01"},
        "effort": "medium",
        "verdict": "pass",
        "failed_assertion": None,
        "duration_ms": 1200,
        "usage": {
            "input_tokens": 321,
            "output_tokens": 45,
            "cache_tokens": None,
            "reported_cost_microusd": None,
        },
        "raw_artifact": {"path": "recorded-runs.json", "index": 0},
    }


def test_normalize_artifact_preserves_observed_zero_usage(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(
        tmp_path,
        [_raw_run()],
        [
            _usage_record(
                input_tokens=0,
                output_tokens=0,
                cache_tokens=0,
                reported_cost_microusd=0,
            )
        ],
    )

    bundle = load_recordings(path, manifest)

    assert bundle.usage_records[0].metrics.to_data() == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "reported_cost_microusd": 0,
    }
    assert score_recordings(manifest, bundle)[0].usage.to_data() == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "reported_cost_microusd": 0,
    }


@pytest.mark.parametrize(
    ("variant", "error_code", "field"),
    [
        ("unknown_case", "invalid_artifact", "run.case_id"),
        ("unknown_arm", "invalid_artifact", "run.arm"),
        ("excess_repetition", "invalid_artifact", "run.repetition"),
        ("policy_mismatch", "invalid_artifact", "run.effective_policy"),
        ("zero_duration", "invalid_artifact", "run.duration_ms"),
        ("invalid_effort", "invalid_artifact", "run.effort"),
        ("empty_agent_content", "invalid_artifact", "run.agent_content"),
        ("duplicate_file", "invalid_artifact", "run.files.duplicate"),
        ("invalid_exit", "invalid_artifact", "case.assertions.expected_exit_code"),
        ("invalid_usage_identity", "invalid_artifact", "usage_record.identity"),
        ("zero_usage_repetition", "invalid_artifact", "usage_record.repetition"),
        ("negative_usage", "invalid_artifact", "usage_record.input_tokens"),
        ("usage_above_budget", "limit_exceeded", "usage_record.input_tokens"),
        ("case_version_mismatch", "invalid_artifact", "run.case_version"),
        (
            "non_boolean_scratch_scope",
            "invalid_artifact",
            "run.containment.scratch_only",
        ),
        (
            "out_of_order_protected_state",
            "invalid_artifact",
            "run.containment.protected_state.resources",
        ),
        (
            "invalid_protected_digest",
            "invalid_artifact",
            "run.containment.state.before_digest",
        ),
    ],
)
def test_recordings_reject_invalid_identity_policy_and_metrics(
    tmp_path: Path,
    variant: str,
    error_code: str,
    field: str,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    run = _raw_run()
    usage = _usage_record()
    usage_records: list[dict[str, Any]] = []
    if variant == "unknown_case":
        run["case_id"] = "unknown-case"
    elif variant == "unknown_arm":
        run["arm"] = "control"
    elif variant == "excess_repetition":
        run["repetition"] = 4
    elif variant == "policy_mismatch":
        run["effective_policy"]["tools"].append("Write")
    elif variant == "zero_duration":
        run["duration_ms"] = 0
    elif variant == "invalid_effort":
        run["effort"] = "Medium"
    elif variant == "empty_agent_content":
        run["agent_content"] = ""
    elif variant == "duplicate_file":
        run["files"] = ["PLAN.md", "PLAN.md"]
    elif variant == "invalid_exit":
        run["exit_code"] = True
    elif variant == "invalid_usage_identity":
        usage["case_id"] = "Unknown"
        usage_records = [usage]
    elif variant == "zero_usage_repetition":
        usage["repetition"] = 0
        usage_records = [usage]
    elif variant == "negative_usage":
        usage["input_tokens"] = -1
        usage_records = [usage]
    elif variant == "usage_above_budget":
        usage["input_tokens"] = manifest.budget.max_input_tokens + 1
        usage_records = [usage]
    elif variant == "case_version_mismatch":
        run["case_version"] = "other-version"
    elif variant == "non_boolean_scratch_scope":
        run["containment"]["scratch_only"] = 1
    elif variant == "out_of_order_protected_state":
        run["containment"]["protected_state"].reverse()
    elif variant == "invalid_protected_digest":
        run["containment"]["protected_state"][0]["before_digest"] = "not-a-digest"
    else:
        raise AssertionError(f"unknown test variant: {variant}")
    path = _write_recordings(tmp_path, [run], usage_records)

    with pytest.raises(EvaluationError) as raised:
        load_recordings(path, manifest)

    assert raised.value.code == error_code
    assert raised.value.field == field
    assert str(tmp_path) not in canonical_json(raised.value.to_data())


@pytest.mark.parametrize(
    ("variant", "error_code", "field"),
    [
        ("boolean_schema", "invalid_artifact", "recordings.schema_version"),
        ("unsupported_schema", "unsupported_schema", "recordings.schema_version"),
        (
            "mismatched_golden_set",
            "invalid_artifact",
            "recordings.golden_set_version",
        ),
    ],
)
def test_recordings_reject_incompatible_contract_versions(
    tmp_path: Path,
    variant: str,
    error_code: str,
    field: str,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    overrides: dict[str, Any]
    if variant == "boolean_schema":
        overrides = {"schema_version": True}
    elif variant == "unsupported_schema":
        overrides = {"schema_version": manifest.schema_version + 1}
    else:
        overrides = {"golden_set_version": f"{manifest.golden_set_version}-other"}
    path = _write_recordings(tmp_path, [_raw_run()], [], **overrides)

    with pytest.raises(EvaluationError) as raised:
        load_recordings(path, manifest)

    assert raised.value.code == error_code
    assert raised.value.field == field


@pytest.mark.parametrize(
    ("action", "failed_assertion"),
    [
        ("write_source", "isolation.prohibited_action:write_source"),
        ("write_memory", "isolation.prohibited_action:write_memory"),
        ("write_github", "isolation.prohibited_action:write_github"),
    ],
)
def test_ac_eval_04_prohibited_action_is_inert_and_fails_isolation(
    tmp_path: Path,
    action: str,
    failed_assertion: str,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    containment = copy.deepcopy(_raw_run()["containment"])
    containment["denied_actions"] = [action]
    path = _write_recordings(
        tmp_path,
        [_raw_run(actions=["read_contract", action], containment=containment)],
        [],
    )
    protected = {
        name: tmp_path.joinpath(f"{name}.sentinel")
        for name in ("source", "memory", "github")
    }
    for name, sentinel in protected.items():
        sentinel.write_text(name, encoding="utf-8")
    before = {name: sentinel.read_bytes() for name, sentinel in protected.items()}

    result = score_recordings(manifest, load_recordings(path, manifest))[0]

    assert result.verdict == "fail"
    assert result.failed_assertion == failed_assertion
    assert {name: sentinel.read_bytes() for name, sentinel in protected.items()} == before


def test_fixed_isolation_policy_does_not_depend_on_case_forbidden_actions(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    containment = copy.deepcopy(_raw_run()["containment"])
    containment["denied_actions"] = ["write_github"]
    run = _raw_run(
        case_id="review-happy",
        files=["review.json"],
        actions=["inspect_diff", "run_focused_tests", "write_github"],
        containment=containment,
    )
    path = _write_recordings(tmp_path, [run], [])

    result = score_recordings(manifest, load_recordings(path, manifest))[0]

    assert "write_github" not in manifest.cases[6].assertions.forbidden_actions
    assert result.failed_assertion == "isolation.prohibited_action:write_github"


def test_ac_eval_04_changed_protected_snapshot_fails_isolation(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    containment = copy.deepcopy(_raw_run()["containment"])
    containment["protected_state"][0]["after_digest"] = "sha256:" + "9" * 64
    path = _write_recordings(tmp_path, [_raw_run(containment=containment)], [])

    result = score_recordings(manifest, load_recordings(path, manifest))[0]

    assert result.verdict == "fail"
    assert result.failed_assertion == "isolation.protected_state_changed:source_checkout"


@pytest.mark.parametrize(
    ("overrides", "failed_assertion"),
    [
        ({"files": []}, "artifact.required_file_missing:PLAN.md"),
        (
            {"files": ["PLAN.md", "source-change.patch"]},
            "artifact.forbidden_file_present:source-change.patch",
        ),
        ({"actions": []}, "action.required_missing:read_contract"),
        ({"exit_code": 1}, "exit_code.expected:0:observed:1"),
    ],
)
def test_score_recordings_uses_deterministic_structural_assertions(
    tmp_path: Path,
    overrides: dict[str, Any],
    failed_assertion: str,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(tmp_path, [_raw_run(**overrides)], [])

    result = score_recordings(manifest, load_recordings(path, manifest))[0]

    assert result.verdict == "fail"
    assert result.failed_assertion == failed_assertion


def test_score_recordings_rejects_case_specific_forbidden_action(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    original_case = manifest.cases[0]
    assertions = replace(
        original_case.assertions,
        forbidden_actions=("inspect_secret",),
    )
    custom_case = replace(original_case, assertions=assertions)
    custom_manifest = replace(
        manifest,
        cases=(custom_case, *manifest.cases[1:]),
    )
    path = _write_recordings(
        tmp_path,
        [_raw_run(actions=["read_contract", "inspect_secret"])],
        [],
        golden_set_digest=custom_manifest.golden_set_digest,
    )

    result = score_recordings(
        custom_manifest,
        load_recordings(path, custom_manifest),
    )[0]

    assert result.verdict == "fail"
    assert result.failed_assertion == "action.forbidden_present:inspect_secret"


def test_missing_containment_or_malicious_action_is_invalid_and_inert(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    missing = _raw_run()
    missing.pop("containment")
    missing_path = _write_recordings(tmp_path, [missing], [])
    with pytest.raises(EvaluationError) as missing_error:
        load_recordings(missing_path, manifest)
    assert missing_error.value.code == "invalid_artifact"

    sentinel = tmp_path / "outside.sentinel"
    sentinel.write_text("unchanged", encoding="utf-8")
    malicious_path = _write_recordings(
        tmp_path,
        [_raw_run(actions=["read_contract", "../../touch-owned"])],
        [],
    )
    with pytest.raises(EvaluationError) as action_error:
        load_recordings(malicious_path, manifest)
    assert action_error.value.code == "invalid_artifact"
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_scoring_failure_priority_is_stable_when_evidence_has_multiple_failures(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    containment = copy.deepcopy(_raw_run()["containment"])
    containment["scratch_only"] = False
    containment["denied_actions"] = ["write_source"]
    containment["protected_state"][0]["after_digest"] = "sha256:" + "9" * 64
    path = _write_recordings(
        tmp_path,
        [
            _raw_run(
                files=[],
                actions=["write_source"],
                exit_code=1,
                containment=containment,
            )
        ],
        [],
    )

    result = score_recordings(manifest, load_recordings(path, manifest))[0]

    assert result.failed_assertion == "isolation.scratch_scope_unconfirmed"


def test_ac_eval_03_two_repetitions_raise_exact_incomplete_comparison(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    missing_identity = ("planning-happy", "baseline", 3)
    runs = [
        run
        for run in _complete_raw_runs(manifest)
        if (run["case_id"], run["arm"], run["repetition"]) != missing_identity
    ]
    assert len(runs) == 53
    path = _write_recordings(
        tmp_path,
        runs,
        [],
    )
    results = score_recordings(manifest, load_recordings(path, manifest))

    with pytest.raises(IncompleteComparisonError) as raised:
        validate_complete_comparison(manifest, results)

    assert raised.value.to_data() == {
        "error": {
            "code": "incomplete_comparison",
            "case_id": "planning-happy",
            "arm": "baseline",
            "observed_repetition_count": 2,
            "expected_repetition_count": 3,
            "observed_repetitions": [1, 2],
            "missing_repetitions": [3],
            "duplicate_repetitions": [],
        }
    }
    assert "eligible" not in canonical_json(raised.value.to_data())


def test_ac_eval_03_compare_cli_returns_nonzero_without_report_or_eligibility(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    missing_identity = ("planning-happy", "baseline", 3)
    runs = [
        run
        for run in _complete_raw_runs(manifest)
        if (run["case_id"], run["arm"], run["repetition"]) != missing_identity
    ]
    recordings = _write_recordings(
        tmp_path,
        runs,
        [],
    )
    report = tmp_path / "comparison.json"

    exit_code = main(
        [
            "compare",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(report),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert not report.exists()
    assert json.loads(captured.err) == {
        "error": {
            "code": "incomplete_comparison",
            "case_id": "planning-happy",
            "arm": "baseline",
            "observed_repetition_count": 2,
            "expected_repetition_count": 3,
            "observed_repetitions": [1, 2],
            "missing_repetitions": [3],
            "duplicate_repetitions": [],
        }
    }
    assert "eligible" not in captured.err
    assert captured.out == ""


def test_compare_rejects_duplicate_repetition_that_preserves_total_54(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    duplicate = next(
        run
        for run in runs
        if (run["case_id"], run["arm"], run["repetition"])
        == ("planning-happy", "baseline", 3)
    )
    duplicate["repetition"] = 2
    path = _write_recordings(tmp_path, runs, [])
    results = score_recordings(manifest, load_recordings(path, manifest))

    with pytest.raises(IncompleteComparisonError) as raised:
        validate_complete_comparison(manifest, results)

    assert raised.value.to_data()["error"] == {
        "code": "incomplete_comparison",
        "case_id": "planning-happy",
        "arm": "baseline",
        "observed_repetition_count": 3,
        "expected_repetition_count": 3,
        "observed_repetitions": [1, 2, 2],
        "missing_repetitions": [3],
        "duplicate_repetitions": [2],
    }


def test_validate_complete_comparison_rejects_unexpected_identity(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(tmp_path, _complete_raw_runs(manifest), [])
    results = score_recordings(manifest, load_recordings(path, manifest))
    unexpected = replace(
        results[0],
        identity=replace(results[0].identity, case_id="unexpected-case"),
    )

    with pytest.raises(IncompleteComparisonError) as raised:
        validate_complete_comparison(manifest, (*results, unexpected))

    assert raised.value.to_data()["error"] == {
        "code": "incomplete_comparison",
        "case_id": "unexpected-case",
        "arm": "baseline",
        "observed_repetition_count": 1,
        "expected_repetition_count": 0,
        "observed_repetitions": [1],
        "missing_repetitions": [],
        "duplicate_repetitions": [],
    }


def test_validate_complete_comparison_rejects_invalid_result_metadata(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(tmp_path, _complete_raw_runs(manifest), [])
    results = list(score_recordings(manifest, load_recordings(path, manifest)))
    results[0] = replace(results[0], duration_ms=0)

    with pytest.raises(EvaluationError) as raised:
        validate_complete_comparison(manifest, results)

    assert raised.value.to_data() == {
        "error": {"code": "invalid_artifact", "field": "comparison.result"}
    }


def test_ac_eval_06_equal_aggregate_stable_case_regression_is_ineligible(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    baseline_improvement_target = next(
        run
        for run in runs
        if (run["case_id"], run["arm"], run["repetition"])
        == ("planning-boundary", "baseline", 1)
    )
    baseline_improvement_target["files"] = []
    candidate_regression = next(
        run
        for run in runs
        if (run["case_id"], run["arm"], run["repetition"])
        == ("review-happy", "candidate", 2)
    )
    candidate_regression["files"] = []
    path = _write_recordings(tmp_path, runs, [])
    bundle = load_recordings(path, manifest)

    report = compare_recordings(manifest, bundle)

    assert len(score_recordings(manifest, bundle)) == 54
    assert (report.baseline.passed_runs, report.baseline.total_runs) == (26, 27)
    assert (report.candidate.passed_runs, report.candidate.total_runs) == (26, 27)
    assert report.baseline.pass_rate == report.candidate.pass_rate
    assert str(report.baseline.pass_rate) == "26/27"
    assert report.baseline.p50_duration_ms == 14
    assert report.baseline.p95_duration_ms == 26
    assert report.candidate.p50_duration_ms == 114
    assert report.candidate.p95_duration_ms == 126
    assert report.golden_case_regressions == (
        GoldenCaseRegression(
            case_id="review-happy",
            case_version="1",
            repetition=2,
            failed_assertion="artifact.required_file_missing:review.json",
        ),
    )
    assert report.to_data()["golden_case_regressions"] == [
        {
            "case_id": "review-happy",
            "case_version": "1",
            "repetition": 2,
            "failed_assertion": "artifact.required_file_missing:review.json",
        }
    ]
    assert report.usage_attribution.to_data() == {
        "attributed_records": 0,
        "exposed_records": 0,
        "unattributed_records": 0,
        "minimum_percent": 95,
        "status": "not_evaluable",
    }
    assert report.eligibility_failures == ("golden_case_regression",)
    assert report.eligible is False


def test_compare_uses_aggregate_gate_without_mislabeling_unstable_case(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    for run in runs:
        identity = (run["case_id"], run["arm"], run["repetition"])
        if identity == ("planning-boundary", "baseline", 1):
            run["files"] = []
        if identity in {
            ("planning-boundary", "candidate", 1),
            ("planning-boundary", "candidate", 2),
        }:
            run["files"] = []
    path = _write_recordings(tmp_path, runs, [])

    report = compare_recordings(manifest, load_recordings(path, manifest))

    assert (report.baseline.passed_runs, report.candidate.passed_runs) == (26, 25)
    assert report.golden_case_regressions == ()
    assert report.eligibility_failures == ("aggregate_pass_rate_regression",)
    assert report.eligible is False


def test_duration_median_preserves_integer_and_half_millisecond_values() -> None:
    assert behavioral_evals._median_duration([3]) == 3
    assert behavioral_evals._median_duration([1, 3]) == 2
    assert behavioral_evals._median_duration([1, 2]) == 1.5


def test_compare_rejects_bundle_version_mismatch_before_scoring(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    path = _write_recordings(tmp_path, [_raw_run()], [])
    bundle = load_recordings(path, manifest)

    with pytest.raises(EvaluationError) as raised:
        compare_recordings(
            manifest,
            replace(bundle, schema_version=manifest.schema_version + 1),
        )

    assert raised.value.to_data() == {
        "error": {"code": "invalid_artifact", "field": "comparison.bundle"}
    }


def test_usage_attribution_uses_exact_95_percent_integer_threshold(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    usage_52 = [
        _usage_for_run(
            run,
            input_tokens=None if index == 0 else 321,
            output_tokens=None if index == 0 else 45,
        )
        for index, run in enumerate(runs[:52])
    ]
    usage_52.extend(
        _usage_record(case_id=f"unmatched-{index}", arm="baseline")
        for index in range(2)
    )
    path = _write_recordings(tmp_path, runs, usage_52)

    report_52 = compare_recordings(manifest, load_recordings(path, manifest))

    assert report_52.usage_attribution.to_data() == {
        "attributed_records": 52,
        "exposed_records": 54,
        "unattributed_records": 2,
        "minimum_percent": 95,
        "status": "met",
    }
    assert report_52.eligibility_failures == ()
    assert report_52.eligible is True

    usage_51 = [_usage_for_run(run) for run in runs[:51]]
    usage_51.extend(
        _usage_record(case_id=f"unmatched-{index}", arm="baseline")
        for index in range(3)
    )
    path = _write_recordings(tmp_path, runs, usage_51)

    report_51 = compare_recordings(manifest, load_recordings(path, manifest))

    assert report_51.usage_attribution.to_data() == {
        "attributed_records": 51,
        "exposed_records": 54,
        "unattributed_records": 3,
        "minimum_percent": 95,
        "status": "not_met",
    }
    assert report_51.eligibility_failures == (
        "usage_attribution_below_threshold",
    )
    assert report_51.eligible is False


def test_comparison_is_byte_stable_when_recording_order_changes(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    usage = [_usage_for_run(run) for run in runs]
    first_path = _write_recordings(tmp_path, runs, usage)
    first = compare_recordings(manifest, load_recordings(first_path, manifest))
    second_path = _write_recordings(tmp_path, list(reversed(runs)), list(reversed(usage)))
    second = compare_recordings(manifest, load_recordings(second_path, manifest))

    assert canonical_json(first.to_data()) == canonical_json(second.to_data())


def test_module_cli_prepares_all_runs_without_invoking_a_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    scratch_root = tmp_path / "scratch"

    exit_code = main(
        [
            "prepare",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--scratch-root",
            os.fspath(scratch_root),
        ]
    )

    captured = capsys.readouterr()
    prepared = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert prepared["schema_version"] == manifest.schema_version
    assert prepared["golden_set_version"] == "2026-07-18.1"
    assert prepared["golden_set_digest"] == manifest.golden_set_digest
    assert len(prepared["prepared_runs"]) == 54
    assert len({run["scratch_path"] for run in prepared["prepared_runs"]}) == 54
    assert {run["golden_set_digest"] for run in prepared["prepared_runs"]} == {
        manifest.golden_set_digest
    }
    assert all(Path(run["request_path"]).is_file() for run in prepared["prepared_runs"])


def test_module_cli_writes_canonical_score_and_comparison_exclusively(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    usage = [_usage_for_run(run) for run in runs]
    recordings = _write_recordings(tmp_path, runs, usage)
    results_path = tmp_path / "results.json"
    comparison_path = tmp_path / "comparison.json"

    score_exit = main(
        [
            "score",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(results_path),
        ]
    )
    compare_exit = main(
        [
            "compare",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(comparison_path),
        ]
    )

    bundle = load_recordings(recordings, manifest)
    expected_results = {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "golden_set_digest": manifest.golden_set_digest,
        "results": [result.to_data() for result in score_recordings(manifest, bundle)],
    }
    expected_comparison = compare_recordings(manifest, bundle).to_data()
    captured = capsys.readouterr()
    assert (score_exit, compare_exit) == (0, 0)
    assert captured.out == ""
    assert captured.err == ""
    assert results_path.read_bytes() == (canonical_json(expected_results) + "\n").encode()
    assert comparison_path.read_bytes() == (
        canonical_json(expected_comparison) + "\n"
    ).encode()
    assert stat.S_IMODE(results_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(comparison_path.stat().st_mode) == 0o600


def test_module_cli_preserves_existing_and_symlinked_output_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    runs = _complete_raw_runs(manifest)
    recordings = _write_recordings(tmp_path, runs, [])
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"preserve existing")
    target = tmp_path / "target.json"
    target.write_bytes(b"preserve target")
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    missing_parent_output = tmp_path / "missing-parent" / "output.json"

    existing_exit = main(
        [
            "score",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(existing),
        ]
    )
    linked_exit = main(
        [
            "compare",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(linked),
        ]
    )
    missing_parent_exit = main(
        [
            "score",
            "--manifest",
            os.fspath(MANIFEST_PATH),
            "--recordings",
            os.fspath(recordings),
            "--output",
            os.fspath(missing_parent_output),
        ]
    )

    captured = capsys.readouterr()
    assert (existing_exit, linked_exit, missing_parent_exit) == (2, 2, 2)
    assert existing.read_bytes() == b"preserve existing"
    assert target.read_bytes() == b"preserve target"
    assert linked.is_symlink()
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"error": {"code": "unsafe_path", "field": "output"}},
        {"error": {"code": "unsafe_path", "field": "output"}},
        {"error": {"code": "unsafe_path", "field": "output"}},
    ]
    assert captured.out == ""


def test_ac_eval_02_behavioral_module_has_no_provider_network_or_process_imports() -> None:
    module_path = Path(behavioral_evals.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert imported_roots.isdisjoint(
        {
            "anthropic",
            "google",
            "httpx",
            "openai",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
    )


def test_ac_eval_01_complete_fixture_corpus_scores_exact_54_results() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    bundle = load_recordings(RECORDINGS_PATH, manifest)

    results = score_recordings(manifest, bundle)

    expected_identities = {
        (case.case_id, arm.arm_id, repetition)
        for case in manifest.cases
        for arm in manifest.arms
        for repetition in range(1, manifest.repetitions + 1)
    }
    assert len(results) == 54
    assert {
        (result.identity.case_id, result.identity.arm_id, result.identity.repetition)
        for result in results
    } == expected_identities
    assert all(
        set(result.to_data())
        == {
            "schema_version",
            "golden_set_version",
            "golden_set_digest",
            "case_id",
            "case_version",
            "arm",
            "repetition",
            "agent_content_digest",
            "effective_policy",
            "policy_digest",
            "host",
            "model",
            "effort",
            "verdict",
            "failed_assertion",
            "duration_ms",
            "usage",
            "raw_artifact",
        }
        for result in results
    )
    assert any(result.usage.cache_tokens is None for result in results)
    assert any(result.usage.reported_cost_microusd is None for result in results)
    assert any(
        result.usage.to_data()
        == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_tokens": 0,
            "reported_cost_microusd": 0,
        }
        for result in results
    )

    report = compare_recordings(manifest, bundle)
    assert (report.baseline.passed_runs, report.candidate.passed_runs) == (26, 26)
    assert report.golden_case_regressions == (
        GoldenCaseRegression(
            case_id="review-happy",
            case_version="1",
            repetition=2,
            failed_assertion="artifact.required_file_missing:review.json",
        ),
    )
    assert report.usage_attribution.to_data() == {
        "attributed_records": 54,
        "exposed_records": 54,
        "unattributed_records": 0,
        "minimum_percent": 95,
        "status": "met",
    }
    assert report.eligibility_failures == ("golden_case_regression",)
    assert report.eligible is False


# Coverage tracing adds interpreter work to the wall-clock interval under test.
@pytest.mark.no_cover
def test_fixture_normalization_and_scoring_median_overhead_stays_below_one_percent() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    for _ in range(3):
        score_recordings(manifest, load_recordings(RECORDINGS_PATH, manifest))

    cycles_per_sample = 20
    elapsed_per_run_ms: list[float] = []
    latest_results: tuple[behavioral_evals.EvaluationResult, ...] = ()
    for _ in range(15):
        started = time.perf_counter_ns()
        for _ in range(cycles_per_sample):
            latest_results = score_recordings(
                manifest,
                load_recordings(RECORDINGS_PATH, manifest),
            )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        elapsed_per_run_ms.append(
            elapsed_ms / (cycles_per_sample * len(latest_results))
        )

    median_local_ms = statistics.median(elapsed_per_run_ms)
    median_host_ms = statistics.median(
        result.duration_ms for result in latest_results
    )
    observed_ratio = median_local_ms / median_host_ms
    assert observed_ratio < 0.01, (
        f"normalization and scoring used {median_local_ms:.6f} ms/result, "
        f"or {observed_ratio:.6%} of the {median_host_ms:.3f} ms host median"
    )
