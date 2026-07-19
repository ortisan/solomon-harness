"""Seed-content integrity contract for behavioral-evaluation evidence."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from solomon_harness import secure_paths
from solomon_harness.behavioral_evals import (
    EvaluationError,
    canonical_json,
    compare_recordings,
    load_manifest,
    load_recordings,
    prepare_pilot,
    score_recordings,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RECORDINGS_PATH = FIXTURE_ROOT / "recorded-runs.json"


def _expected_golden_set_digest(manifest_data: dict[str, Any], fixture_root: Path) -> str:
    seed_files: list[dict[str, str]] = []
    for case in manifest_data["cases"]:
        fixture_path = case["fixture_path"]
        case_root = fixture_root / fixture_path
        for path in sorted(item for item in case_root.rglob("*") if item.is_file()):
            relative_path = path.relative_to(fixture_root).as_posix()
            content_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            seed_files.append(
                {"path": relative_path, "content_digest": content_digest}
            )
    payload = {
        "manifest": manifest_data,
        "seed_files": sorted(seed_files, key=lambda item: item["path"]),
    }
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _write_recordings(tmp_path: Path, data: dict[str, Any], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_canonical_seed_digest_is_carried_through_all_evidence_layers(
    tmp_path: Path,
) -> None:
    manifest_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest(MANIFEST_PATH)
    expected_digest = _expected_golden_set_digest(manifest_data, FIXTURE_ROOT)

    assert manifest.schema_version == 2
    assert manifest.golden_set_digest == expected_digest

    prepared = prepare_pilot(manifest, tmp_path / "scratch")
    request = json.loads(prepared[0].request_path.read_text(encoding="utf-8"))
    assert prepared[0].golden_set_digest == expected_digest
    assert request["golden_set_digest"] == expected_digest

    bundle = load_recordings(RECORDINGS_PATH, manifest)
    results = score_recordings(manifest, bundle)
    comparison = compare_recordings(manifest, bundle)

    assert bundle.golden_set_digest == expected_digest
    assert bundle.to_data()["golden_set_digest"] == expected_digest
    assert {result.golden_set_digest for result in results} == {expected_digest}
    assert {result.to_data()["golden_set_digest"] for result in results} == {
        expected_digest
    }
    assert comparison.golden_set_digest == expected_digest
    assert comparison.to_data()["golden_set_digest"] == expected_digest


def test_prepare_rejects_in_place_seed_mutation_before_creating_scratch(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    manifest = load_manifest(fixture_root / "manifest.json")
    seed = fixture_root / "cases" / "planning-happy" / "task.txt"
    original_inode = seed.stat().st_ino
    seed.write_text("tampered after manifest validation\n", encoding="utf-8")

    assert seed.stat().st_ino == original_inode
    scratch_root = tmp_path / "scratch"
    with pytest.raises(EvaluationError) as raised:
        prepare_pilot(manifest, scratch_root)

    assert raised.value.code == "unsafe_path"
    assert raised.value.field == "fixture.integrity"
    assert not scratch_root.exists()


def test_v2_manifest_load_rejects_an_unsafe_seed_corpus(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    seed = fixture_root / "cases" / "planning-happy" / "task.txt"
    outside = tmp_path / "outside.txt"
    outside.write_text("must not enter the golden set\n", encoding="utf-8")
    seed.unlink()
    seed.symlink_to(outside)

    with pytest.raises(EvaluationError) as raised:
        load_manifest(fixture_root / "manifest.json")

    assert raised.value.code == "unsafe_path"
    assert raised.value.field == "fixture.entry"


def test_manifest_rejects_seed_swapped_to_external_hard_link_between_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    external = tmp_path / "external.txt"
    external.write_text("outside golden content\n", encoding="utf-8")
    real_stat_at = secure_paths.stat_at
    swapped = False

    def swap_before_inner_stat(parent_fd: int, name: str) -> os.stat_result | None:
        nonlocal swapped
        if name == "task.txt" and not swapped:
            os.rename(
                "task.txt",
                "task-original.txt",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.link(external, "task.txt", dst_dir_fd=parent_fd)
            swapped = True
        return real_stat_at(parent_fd, name)

    monkeypatch.setattr(secure_paths, "stat_at", swap_before_inner_stat)

    with pytest.raises(EvaluationError) as raised:
        load_manifest(fixture_root / "manifest.json")

    assert swapped is True
    assert raised.value.code == "unsafe_path"
    assert raised.value.field == "fixture.entry"


def test_v2_recordings_require_the_prepared_golden_set_digest(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    recordings = json.loads(RECORDINGS_PATH.read_text(encoding="utf-8"))

    missing = dict(recordings)
    missing.pop("golden_set_digest")
    with pytest.raises(EvaluationError) as missing_error:
        load_recordings(_write_recordings(tmp_path, missing, "missing.json"), manifest)
    assert missing_error.value.code == "invalid_artifact"
    assert missing_error.value.field == "recordings.fields"

    mismatched = dict(recordings)
    mismatched["golden_set_digest"] = "sha256:" + "0" * 64
    with pytest.raises(EvaluationError) as mismatch_error:
        load_recordings(
            _write_recordings(tmp_path, mismatched, "mismatched.json"), manifest
        )
    assert mismatch_error.value.code == "invalid_artifact"
    assert mismatch_error.value.field == "recordings.golden_set_digest"
