from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, cast

import pytest

from solomon_harness import behavioral_evals as evals


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RECORDINGS_PATH = FIXTURE_ROOT / "recorded-runs.json"


def _artifact_loader(name: str) -> Callable[[Path, evals.EvaluationManifest], object]:
    loader = getattr(evals, name, None)
    assert callable(loader), f"behavioral_evals.{name} must be a public closed parser"
    return loader


def _write_json(path: Path, value: object) -> None:
    path.write_text(evals.canonical_json(value) + "\n", encoding="utf-8")


def _valid_artifacts() -> tuple[
    evals.EvaluationManifest,
    dict[str, object],
    dict[str, object],
]:
    manifest = evals.load_manifest(MANIFEST_PATH)
    recordings = evals.load_recordings(RECORDINGS_PATH, manifest)
    results = evals.score_recordings(manifest, recordings)
    result_artifact = {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "golden_set_digest": manifest.golden_set_digest,
        "results": [result.to_data() for result in results],
    }
    comparison_artifact = evals.compare_recordings(manifest, recordings).to_data()
    return manifest, result_artifact, comparison_artifact


def test_load_results_round_trips_closed_contract(tmp_path: Path) -> None:
    manifest, result_artifact, _comparison_artifact = _valid_artifacts()
    result_path = tmp_path / "results.json"
    _write_json(result_path, result_artifact)

    parsed = cast(
        tuple[evals.EvaluationResult, ...],
        _artifact_loader("load_results")(result_path, manifest),
    )

    assert [result.to_data() for result in parsed] == result_artifact["results"]


def test_load_results_rejects_unknown_nested_field(tmp_path: Path) -> None:
    manifest, result_artifact, _comparison_artifact = _valid_artifacts()
    raw_results = result_artifact["results"]
    assert isinstance(raw_results, list)
    first = raw_results[0]
    assert isinstance(first, dict)
    first["unexpected"] = True
    result_path = tmp_path / "results.json"
    _write_json(result_path, result_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_results")(result_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "result.fields"


def test_load_results_rejects_unsupported_schema_before_shape_validation(
    tmp_path: Path,
) -> None:
    manifest, result_artifact, _comparison_artifact = _valid_artifacts()
    result_artifact["schema_version"] = 1
    result_artifact["unexpected"] = True
    result_path = tmp_path / "results.json"
    _write_json(result_path, result_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_results")(result_path, manifest)

    assert raised.value.code == "unsupported_schema"
    assert raised.value.field == "results.schema_version"


def test_load_results_rejects_mismatched_golden_set_digest(tmp_path: Path) -> None:
    manifest, result_artifact, _comparison_artifact = _valid_artifacts()
    result_artifact["golden_set_digest"] = "sha256:" + "0" * 64
    result_path = tmp_path / "results.json"
    _write_json(result_path, result_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_results")(result_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "results.golden_set_digest"


def test_load_results_rejects_duplicate_run_identity(tmp_path: Path) -> None:
    manifest, result_artifact, _comparison_artifact = _valid_artifacts()
    results = result_artifact["results"]
    assert isinstance(results, list)
    results.append(dict(results[0]))
    result_path = tmp_path / "results.json"
    _write_json(result_path, result_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_results")(result_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "results.identity.duplicate"


def test_load_comparison_round_trips_closed_contract(tmp_path: Path) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    parsed = cast(
        evals.ComparisonReport,
        _artifact_loader("load_comparison")(comparison_path, manifest),
    )

    assert parsed.to_data() == comparison_artifact


def test_load_comparison_rejects_unknown_nested_field(tmp_path: Path) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    baseline = comparison_artifact["baseline"]
    assert isinstance(baseline, dict)
    baseline["unexpected"] = True
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.arm.fields"


def test_load_comparison_rejects_half_integer_median_for_odd_sample_count(
    tmp_path: Path,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    baseline = comparison_artifact["baseline"]
    assert isinstance(baseline, dict)
    baseline["p50_duration_ms"] = 14.5
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.arm.p50_duration_ms"


def test_load_comparison_accepts_half_integer_median_for_even_sample_count(
    tmp_path: Path,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    extra_case = replace(manifest.cases[0], case_id="planning-extra")
    even_manifest = replace(manifest, cases=(*manifest.cases, extra_case))
    comparison_artifact["golden_set_digest"] = even_manifest.golden_set_digest
    for arm_name in ("baseline", "candidate"):
        arm = comparison_artifact[arm_name]
        assert isinstance(arm, dict)
        arm["total_runs"] = len(even_manifest.cases) * even_manifest.repetitions
    baseline = comparison_artifact["baseline"]
    assert isinstance(baseline, dict)
    baseline["p50_duration_ms"] = 14.5
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    parsed = cast(
        evals.ComparisonReport,
        _artifact_loader("load_comparison")(comparison_path, even_manifest),
    )

    assert parsed.baseline.p50_duration_ms == 14.5


def test_load_comparison_rejects_duplicate_regression_identity(
    tmp_path: Path,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    regressions = comparison_artifact["golden_case_regressions"]
    assert isinstance(regressions, list)
    duplicate = dict(regressions[0])
    duplicate["failed_assertion"] = "action.required_missing:review"
    regressions.append(duplicate)
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.golden_case_regressions.duplicate"


@pytest.mark.parametrize("inconsistency", ["candidate_failures", "stable_baseline"])
def test_load_comparison_rejects_impossible_regression_summary(
    tmp_path: Path,
    inconsistency: str,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    if inconsistency == "candidate_failures":
        candidate = comparison_artifact["candidate"]
        assert isinstance(candidate, dict)
        candidate["passed_runs"] = candidate["total_runs"]
    else:
        baseline = comparison_artifact["baseline"]
        assert isinstance(baseline, dict)
        baseline["passed_runs"] = manifest.repetitions - 1
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.golden_case_regressions"


def test_load_comparison_rejects_inconsistent_derived_eligibility(
    tmp_path: Path,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    comparison_artifact["eligible"] = True
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.eligible"


def test_load_comparison_rejects_more_attributions_than_run_identities(
    tmp_path: Path,
) -> None:
    manifest, _result_artifact, comparison_artifact = _valid_artifacts()
    attribution = comparison_artifact["usage_attribution"]
    assert isinstance(attribution, dict)
    impossible_count = 2 * len(manifest.cases) * manifest.repetitions + 1
    attribution.update(
        {
            "attributed_records": impossible_count,
            "exposed_records": impossible_count,
            "unattributed_records": 0,
            "status": "met",
        }
    )
    comparison_path = tmp_path / "comparison.json"
    _write_json(comparison_path, comparison_artifact)

    with pytest.raises(evals.EvaluationError) as raised:
        _artifact_loader("load_comparison")(comparison_path, manifest)

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "comparison.usage_attribution.attributed_records"


def test_prepare_packet_contains_complete_inert_assertion_contract(tmp_path: Path) -> None:
    manifest = evals.load_manifest(MANIFEST_PATH)

    prepared = evals.prepare_pilot(manifest, tmp_path / "scratch")
    packet = json.loads(prepared[0].request_path.read_text(encoding="utf-8"))

    assert packet["artifact_contract"] == manifest.cases[0].assertions.to_data()
