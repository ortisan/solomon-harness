"""Contract tests for the offline behavioral-evaluation core (#369)."""

import copy
import hashlib
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
) -> Path:
    path = tmp_path / "recorded-runs.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "golden_set_version": "2026-07-18.1",
                "runs": runs,
                "usage_records": usage_records,
            }
        ),
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
    original_seed = first[0].workspace_path.joinpath("task.txt").read_bytes()
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
    assert second[0].workspace_path.joinpath("task.txt").read_bytes() == original_seed


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


def test_normalize_artifact_preserves_usage_and_marks_missing_metrics_unavailable(
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
        "schema_version": 1,
        "golden_set_version": "2026-07-18.1",
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
