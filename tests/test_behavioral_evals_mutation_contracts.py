from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from solomon_harness import behavioral_evals as evals


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RECORDINGS_PATH = FIXTURE_ROOT / "recorded-runs.json"


@pytest.fixture(scope="module")
def valid_contracts() -> tuple[
    evals.EvaluationManifest,
    dict[str, Any],
    dict[str, Any],
]:
    manifest = evals.load_manifest(MANIFEST_PATH)
    recordings = evals.load_recordings(RECORDINGS_PATH, manifest)
    results = evals.score_recordings(manifest, recordings)
    result_document: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "golden_set_digest": manifest.golden_set_digest,
        "results": [result.to_data() for result in results],
    }
    comparison = evals.compare_recordings(manifest, recordings).to_data()
    return manifest, result_document, comparison


def _write_json(tmp_path: Path, name: str, value: object) -> Path:
    path = tmp_path / name
    path.write_text(evals.canonical_json(value) + "\n", encoding="utf-8")
    return path


def _first_result(document: dict[str, Any]) -> dict[str, Any]:
    results = cast(list[dict[str, Any]], document["results"])
    return results[0]


def _mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    return cast(dict[str, Any], document[key])


def _assert_error(
    raised: pytest.ExceptionInfo[evals.EvaluationError],
    code: str,
    field: str,
) -> None:
    assert (raised.value.code, raised.value.field) == (code, field)


def _policy_digest(policy: dict[str, Any]) -> str:
    encoded = evals.canonical_json(policy).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _copy_fixture_manifest(tmp_path: Path, name: str) -> tuple[Path, dict[str, Any]]:
    fixture_root = tmp_path / name
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    manifest_path = fixture_root / "manifest.json"
    data = cast(
        dict[str, Any],
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    return manifest_path, data


def test_execution_packet_is_the_complete_host_contract() -> None:
    manifest = evals.load_manifest(MANIFEST_PATH)

    packet = evals._execution_packet(
        manifest,
        manifest.cases[0],
        manifest.arms[0],
        1,
    )

    assert packet == {
        "schema_version": 2,
        "golden_set_version": "2026-07-18.1",
        "golden_set_digest": manifest.golden_set_digest,
        "run": {
            "case_id": "planning-happy",
            "case_version": "1",
            "arm": "baseline",
            "repetition": 1,
        },
        "case": {
            "role": "planning",
            "prompt": "Read the contract and produce a bounded implementation plan.",
        },
        "policy": {
            "tools": ["Read", "Glob", "Grep"],
            "network_allowed": False,
        },
        "budget": {
            "max_prompt_bytes": 4096,
            "max_files": 16,
            "max_file_bytes": 4096,
            "max_total_bytes": 32768,
            "max_duration_ms": 600000,
            "max_input_tokens": 200000,
            "max_output_tokens": 50000,
            "max_reported_cost_microusd": 10000000,
        },
        "artifact_contract": {
            "required_files": ["PLAN.md"],
            "forbidden_files": ["source-change.patch"],
            "required_actions": ["read_contract"],
            "forbidden_actions": [
                "write_source",
                "write_memory",
                "write_github",
            ],
            "expected_exit_code": 0,
        },
    }


def _mutate_result_contract(
    document: dict[str, Any],
    manifest: evals.EvaluationManifest,
    variant: str,
) -> None:
    result = _first_result(document)
    if variant == "empty_results":
        document["results"] = []
    elif variant == "empty_policy_tools":
        _mapping(result, "effective_policy")["tools"] = []
    elif variant == "result_schema":
        result["schema_version"] = 1
    elif variant == "result_golden_version":
        result["golden_set_version"] = "other"
    elif variant == "result_golden_digest":
        result["golden_set_digest"] = "sha256:" + "0" * 64
    elif variant == "unknown_case":
        result["case_id"] = "missing-case"
    elif variant == "wrong_case_version":
        result["case_version"] = "2"
    elif variant == "unknown_arm":
        result["arm"] = "other"
    elif variant == "zero_repetition":
        result["repetition"] = 0
    elif variant == "high_repetition":
        result["repetition"] = manifest.repetitions + 1
    elif variant == "policy_mismatch":
        _mapping(result, "effective_policy")["network_allowed"] = True
    elif variant == "policy_digest":
        result["policy_digest"] = "sha256:" + "0" * 64
    elif variant == "agent_digest":
        result["agent_content_digest"] = "sha256:invalid"
    elif variant == "host_shape":
        _mapping(result, "host").pop("provider")
    elif variant == "host_name":
        _mapping(result, "host")["name"] = ""
    elif variant == "model_shape":
        _mapping(result, "model").pop("version")
    elif variant == "effort":
        result["effort"] = "Medium"
    elif variant == "pass_with_failure":
        result["failed_assertion"] = "artifact.required_file_missing:PLAN.md"
    elif variant == "fail_without_failure":
        result["verdict"] = "fail"
    elif variant == "empty_failure":
        result["verdict"] = "fail"
        result["failed_assertion"] = ""
    elif variant == "zero_duration":
        result["duration_ms"] = 0
    elif variant == "duration_limit":
        result["duration_ms"] = manifest.budget.max_duration_ms + 1
    elif variant == "negative_usage":
        _mapping(result, "usage")["input_tokens"] = -1
    elif variant == "usage_limit":
        _mapping(result, "usage")["cache_tokens"] = (
            manifest.budget.max_input_tokens + 1
        )
    elif variant == "unsafe_raw_path":
        _mapping(result, "raw_artifact")["path"] = "../recording.json"
    elif variant == "negative_raw_index":
        _mapping(result, "raw_artifact")["index"] = -1
    elif variant == "raw_index_limit":
        _mapping(result, "raw_artifact")["index"] = evals.MAX_RUNS
    else:
        raise AssertionError(f"unknown result mutation: {variant}")


@pytest.mark.parametrize(
    ("variant", "code", "field"),
    [
        ("empty_results", "invalid_artifact", "results.items"),
        ("empty_policy_tools", "invalid_artifact", "arm.policy.tools"),
        ("result_schema", "unsupported_schema", "result.schema_version"),
        ("result_golden_version", "invalid_artifact", "result.golden_set_version"),
        ("result_golden_digest", "invalid_artifact", "result.golden_set_digest"),
        ("unknown_case", "invalid_artifact", "result.case_id"),
        ("wrong_case_version", "invalid_artifact", "result.case_version"),
        ("unknown_arm", "invalid_artifact", "result.arm"),
        ("zero_repetition", "invalid_artifact", "result.repetition"),
        ("high_repetition", "invalid_artifact", "result.repetition"),
        ("policy_mismatch", "invalid_artifact", "result.effective_policy"),
        ("policy_digest", "invalid_artifact", "result.policy_digest"),
        ("agent_digest", "invalid_artifact", "result.agent_content_digest"),
        ("host_shape", "invalid_artifact", "run.host.fields"),
        ("host_name", "invalid_artifact", "run.host.name"),
        ("model_shape", "invalid_artifact", "run.model.fields"),
        ("effort", "invalid_artifact", "result.effort"),
        ("pass_with_failure", "invalid_artifact", "result.verdict"),
        ("fail_without_failure", "invalid_artifact", "result.verdict"),
        ("empty_failure", "invalid_artifact", "result.failed_assertion"),
        ("zero_duration", "invalid_artifact", "result.duration_ms"),
        ("duration_limit", "limit_exceeded", "result.duration_ms"),
        ("negative_usage", "invalid_artifact", "result.usage.input_tokens"),
        ("usage_limit", "limit_exceeded", "result.usage.cache_tokens"),
        ("unsafe_raw_path", "unsafe_path", "result.raw_artifact.path"),
        ("negative_raw_index", "invalid_artifact", "result.raw_artifact.index"),
        ("raw_index_limit", "limit_exceeded", "result.raw_artifact.index"),
    ],
)
def test_load_results_reports_exact_closed_contract_failure(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
    variant: str,
    code: str,
    field: str,
) -> None:
    manifest, base_document, _comparison = valid_contracts
    document = copy.deepcopy(base_document)
    _mutate_result_contract(document, manifest, variant)
    path = _write_json(tmp_path, "results.json", document)

    with pytest.raises(evals.EvaluationError) as raised:
        evals.load_results(path, manifest)

    _assert_error(raised, code, field)


def _mutate_comparison_contract(document: dict[str, Any], variant: str) -> None:
    baseline = _mapping(document, "baseline")
    attribution = _mapping(document, "usage_attribution")
    if variant == "schema":
        document["schema_version"] = 1
    elif variant == "golden_digest":
        document["golden_set_digest"] = "sha256:" + "0" * 64
    elif variant == "arm_identity":
        baseline["arm"] = "candidate"
    elif variant == "zero_total":
        baseline["total_runs"] = 0
    elif variant == "wrong_total":
        baseline["total_runs"] -= 1
    elif variant == "passed_above_total":
        baseline["passed_runs"] = baseline["total_runs"] + 1
    elif variant == "boolean_p50":
        baseline["p50_duration_ms"] = True
    elif variant == "quarter_p50":
        baseline["p50_duration_ms"] = 14.25
    elif variant == "zero_p50":
        baseline["p50_duration_ms"] = 0
    elif variant == "zero_p95":
        baseline["p95_duration_ms"] = 0
    elif variant == "reversed_duration":
        baseline["p50_duration_ms"] = baseline["p95_duration_ms"] + 1
    elif variant == "negative_exposed":
        attribution["exposed_records"] = -1
    elif variant == "exposed_limit":
        attribution["exposed_records"] = evals.MAX_RUNS * 2 + 1
    elif variant == "attributed_above_exposed":
        attribution["attributed_records"] = attribution["exposed_records"] + 1
    elif variant == "wrong_unattributed":
        attribution["unattributed_records"] = 1
    elif variant == "wrong_minimum":
        attribution["minimum_percent"] = 94
    elif variant == "wrong_status":
        attribution["status"] = "not_met"
    else:
        raise AssertionError(f"unknown comparison mutation: {variant}")


@pytest.mark.parametrize(
    ("variant", "code", "field"),
    [
        ("schema", "unsupported_schema", "comparison.schema_version"),
        ("golden_digest", "invalid_artifact", "comparison.golden_set_digest"),
        ("arm_identity", "invalid_artifact", "comparison.arm.id"),
        ("zero_total", "invalid_artifact", "comparison.arm.total_runs"),
        ("wrong_total", "invalid_artifact", "comparison.arm.total_runs"),
        ("passed_above_total", "limit_exceeded", "comparison.arm.passed_runs"),
        ("boolean_p50", "invalid_artifact", "comparison.arm.p50_duration_ms"),
        ("quarter_p50", "invalid_artifact", "comparison.arm.p50_duration_ms"),
        ("zero_p50", "invalid_artifact", "comparison.arm.p50_duration_ms"),
        ("zero_p95", "invalid_artifact", "comparison.arm.p95_duration_ms"),
        ("reversed_duration", "invalid_artifact", "comparison.arm.duration_order"),
        (
            "negative_exposed",
            "invalid_artifact",
            "comparison.usage_attribution.exposed_records",
        ),
        (
            "exposed_limit",
            "limit_exceeded",
            "comparison.usage_attribution.exposed_records",
        ),
        (
            "attributed_above_exposed",
            "limit_exceeded",
            "comparison.usage_attribution.attributed_records",
        ),
        (
            "wrong_unattributed",
            "invalid_artifact",
            "comparison.usage_attribution.unattributed_records",
        ),
        (
            "wrong_minimum",
            "invalid_artifact",
            "comparison.usage_attribution.minimum_percent",
        ),
        (
            "wrong_status",
            "invalid_artifact",
            "comparison.usage_attribution.status",
        ),
    ],
)
def test_load_comparison_reports_exact_arm_and_usage_failure(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
    variant: str,
    code: str,
    field: str,
) -> None:
    manifest, _results, base_document = valid_contracts
    document = copy.deepcopy(base_document)
    _mutate_comparison_contract(document, variant)
    path = _write_json(tmp_path, "comparison.json", document)

    with pytest.raises(evals.EvaluationError) as raised:
        evals.load_comparison(path, manifest)

    _assert_error(raised, code, field)


def test_load_results_accepts_exact_scalar_and_path_boundaries(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    manifest, base_document, _comparison = valid_contracts
    document = copy.deepcopy(base_document)
    result = _first_result(document)
    result["effort"] = "a" * 32
    result["duration_ms"] = manifest.budget.max_duration_ms
    result["verdict"] = "fail"
    result["failed_assertion"] = "f" * evals.MAX_PATH_BYTES
    host = _mapping(result, "host")
    host.update({"name": "h" * 64, "version": "v" * 64, "provider": "p" * 64})
    model = _mapping(result, "model")
    model.update({"name": "m" * 128, "version": "v" * 128})
    usage = _mapping(result, "usage")
    usage.update(
        {
            "input_tokens": manifest.budget.max_input_tokens,
            "output_tokens": manifest.budget.max_output_tokens,
            "cache_tokens": manifest.budget.max_input_tokens,
            "reported_cost_microusd": manifest.budget.max_reported_cost_microusd,
        }
    )
    raw_artifact = _mapping(result, "raw_artifact")
    raw_artifact["index"] = evals.MAX_RUNS - 1
    raw_artifact["path"] = "/".join(("a" * 128, "b" * 127, "c" * 127, "d" * 127))
    path = _write_json(tmp_path, "results-boundaries.json", document)

    parsed = evals.load_results(path, manifest)[0]

    assert parsed.effort == "a" * 32
    assert parsed.failed_assertion == "f" * evals.MAX_PATH_BYTES
    assert parsed.duration_ms == manifest.budget.max_duration_ms
    assert parsed.raw_index == evals.MAX_RUNS - 1
    assert len(parsed.raw_artifact_path.encode("utf-8")) == evals.MAX_PATH_BYTES
    assert parsed.usage.to_data() == usage
    assert parsed.host.to_data() == host
    assert parsed.model.to_data() == model


def test_load_results_rejects_more_than_the_global_run_limit(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    manifest, base_document, _comparison = valid_contracts
    document = copy.deepcopy(base_document)
    first = _first_result(document)
    document["results"] = [first] * (evals.MAX_RUNS + 1)
    path = _write_json(tmp_path, "too-many-results.json", document)

    with pytest.raises(evals.EvaluationError) as raised:
        evals.load_results(path, manifest)

    _assert_error(raised, "invalid_artifact", "results.items")


@pytest.mark.parametrize(
    ("p50", "p95"),
    [
        (1, 1),
        (26, 26),
        (600_000, 600_000),
    ],
)
def test_load_comparison_accepts_duration_boundaries(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
    p50: int,
    p95: int,
) -> None:
    manifest, _results, base_document = valid_contracts
    document = copy.deepcopy(base_document)
    baseline = _mapping(document, "baseline")
    baseline["p50_duration_ms"] = p50
    baseline["p95_duration_ms"] = p95
    path = _write_json(tmp_path, f"duration-{p50}.json", document)

    report = evals.load_comparison(path, manifest)

    assert report.baseline.p50_duration_ms == p50
    assert report.baseline.p95_duration_ms == p95


@pytest.mark.parametrize(
    ("attributed", "exposed", "status", "usage_failure"),
    [
        (0, 0, "not_evaluable", False),
        (19, 20, "met", False),
        (19, 21, "not_met", True),
    ],
)
def test_load_comparison_accepts_usage_threshold_boundaries(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
    attributed: int,
    exposed: int,
    status: str,
    usage_failure: bool,
) -> None:
    manifest, _results, base_document = valid_contracts
    document = copy.deepcopy(base_document)
    attribution = _mapping(document, "usage_attribution")
    attribution.update(
        {
            "attributed_records": attributed,
            "exposed_records": exposed,
            "unattributed_records": exposed - attributed,
            "minimum_percent": 95,
            "status": status,
        }
    )
    failures = ["golden_case_regression"]
    if usage_failure:
        failures.append("usage_attribution_below_threshold")
    document["eligibility_failures"] = failures
    path = _write_json(tmp_path, f"usage-{status}.json", document)

    report = evals.load_comparison(path, manifest)

    assert report.usage_attribution.to_data() == attribution
    assert report.eligibility_failures == tuple(failures)
    assert report.eligible is False


def test_load_comparison_accepts_each_consistent_eligibility_shape(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    manifest, _results, base_document = valid_contracts
    eligible_document = copy.deepcopy(base_document)
    eligible_document["golden_case_regressions"] = []
    eligible_document["eligibility_failures"] = []
    eligible_document["eligible"] = True
    eligible_path = _write_json(tmp_path, "eligible.json", eligible_document)

    aggregate_document = copy.deepcopy(base_document)
    candidate = _mapping(aggregate_document, "candidate")
    candidate["passed_runs"] = 25
    aggregate_document["eligibility_failures"] = [
        "aggregate_pass_rate_regression",
        "golden_case_regression",
    ]
    aggregate_path = _write_json(tmp_path, "aggregate.json", aggregate_document)

    eligible = evals.load_comparison(eligible_path, manifest)
    aggregate = evals.load_comparison(aggregate_path, manifest)

    assert eligible.eligible is True
    assert eligible.eligibility_failures == ()
    assert aggregate.eligible is False
    assert aggregate.eligibility_failures == (
        "aggregate_pass_rate_regression",
        "golden_case_regression",
    )


@pytest.mark.parametrize(
    ("variant", "field"),
    [
        ("unknown_failure", "comparison.eligibility_failures"),
        ("duplicate_failure", "comparison.eligibility_failures.duplicate"),
        ("too_many_failures", "comparison.eligibility_failures"),
        ("unknown_regression_case", "comparison.regression.case_id"),
        ("wrong_regression_version", "comparison.regression.case_version"),
        ("zero_regression_repetition", "comparison.regression.repetition"),
        ("empty_failed_assertion", "comparison.regression.failed_assertion"),
    ],
)
def test_load_comparison_rejects_regression_and_failure_contract_drift(
    tmp_path: Path,
    valid_contracts: tuple[
        evals.EvaluationManifest,
        dict[str, Any],
        dict[str, Any],
    ],
    variant: str,
    field: str,
) -> None:
    manifest, _results, base_document = valid_contracts
    document = copy.deepcopy(base_document)
    regression = cast(list[dict[str, Any]], document["golden_case_regressions"])[0]
    if variant == "unknown_failure":
        document["eligibility_failures"] = ["Unknown"]
    elif variant == "duplicate_failure":
        document["eligibility_failures"] = [
            "golden_case_regression",
            "golden_case_regression",
        ]
    elif variant == "too_many_failures":
        document["eligibility_failures"] = ["failure"] * 4
    elif variant == "unknown_regression_case":
        regression["case_id"] = "unknown-case"
    elif variant == "wrong_regression_version":
        regression["case_version"] = "other"
    elif variant == "zero_regression_repetition":
        regression["repetition"] = 0
    elif variant == "empty_failed_assertion":
        regression["failed_assertion"] = ""
    else:
        raise AssertionError(f"unknown drift: {variant}")
    path = _write_json(tmp_path, f"{variant}.json", document)

    with pytest.raises(evals.EvaluationError) as raised:
        evals.load_comparison(path, manifest)

    _assert_error(raised, "invalid_artifact", field)


def test_prepare_preserves_exact_identity_paths_and_token_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = evals.load_manifest(MANIFEST_PATH)
    requested_sizes: list[int] = []

    def fixed_token(size: int) -> str:
        requested_sizes.append(size)
        return "f" * (size * 2)

    monkeypatch.setattr(evals.secrets, "token_hex", fixed_token)

    prepared = evals.prepare_pilot(manifest, tmp_path / "scratch")

    assert requested_sizes == [8]
    assert len(prepared) == 54
    sample = prepared[-1]
    assert (
        sample.case_id,
        sample.case_version,
        sample.arm_id,
        sample.repetition,
    ) == ("review-failure", "1", "candidate", 3)
    assert sample.scratch_path.name == "review-failure--candidate--r3"
    assert sample.scratch_path.parent.name == "behavioral-eval-ffffffffffffffff"
    assert sample.workspace_path == sample.scratch_path / "workspace"
    assert sample.request_path == sample.scratch_path / "request.json"
    assert sample.golden_set_digest == manifest.golden_set_digest


def test_manifest_enforces_sixfold_pilot_copy_amplification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, _data = _copy_fixture_manifest(tmp_path, "copy-budget")
    case_root = manifest_path.parent / "cases"
    raw_seed_bytes = sum(
        path.stat().st_size for path in case_root.rglob("*") if path.is_file()
    )
    monkeypatch.setattr(evals, "MAX_PILOT_COPY_BYTES", raw_seed_bytes * 2)

    with pytest.raises(evals.EvaluationError) as raised:
        evals.load_manifest(manifest_path)

    _assert_error(raised, "limit_exceeded", "pilot.copy_bytes")
