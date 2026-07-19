"""Security regressions for bounded behavioral-evaluation inputs and fixtures."""

import shutil
from pathlib import Path

import pytest

from solomon_harness import behavioral_evals
from solomon_harness.behavioral_evals import (
    EvaluationError,
    load_manifest,
    load_recordings,
    main,
    prepare_pilot,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ("[" * 2_000 + "0" + "]" * 2_000, "json.structure"),
        (
            MANIFEST_PATH.read_text(encoding="utf-8").replace(
                '"schema_version": 1',
                '"schema_version": ' + "9" * 5_000,
                1,
            ),
            "json.integer",
        ),
        (
            MANIFEST_PATH.read_text(encoding="utf-8").replace(
                '"repetitions": 3',
                '"repetitions": 3.0',
                1,
            ),
            "json.float",
        ),
    ],
)
def test_hostile_json_fails_closed_without_cli_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: str,
    field: str,
) -> None:
    manifest_path = tmp_path / "hostile-manifest.json"
    manifest_path.write_text(payload, encoding="utf-8")
    output_path = tmp_path / "comparison.json"

    with pytest.raises(EvaluationError) as raised:
        load_manifest(manifest_path)

    assert raised.value.code == "invalid_manifest"
    assert raised.value.field == field
    assert main(
        [
            "compare",
            "--manifest",
            str(manifest_path),
            "--recordings",
            str(tmp_path / "recordings-with-secret-name.json"),
            "--output",
            str(output_path),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.err
    assert "recordings-with-secret-name" not in captured.err
    assert not output_path.exists()


def test_recordings_reject_float_as_closed_artifact_error(tmp_path: Path) -> None:
    path = tmp_path / "recordings.json"
    path.write_text('{"unexpected":1.5}', encoding="utf-8")

    with pytest.raises(EvaluationError) as raised:
        load_recordings(path, load_manifest(MANIFEST_PATH))

    assert raised.value.code == "invalid_artifact"
    assert raised.value.field == "json.float"


@pytest.mark.parametrize(
    ("limit_name", "expected_field"),
    [
        ("entries", "fixture.entries"),
        ("directories", "fixture.directories"),
    ],
)
def test_seed_scan_enforces_global_entry_and_directory_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    expected_field: str,
) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    if limit_name == "entries":
        monkeypatch.setattr(behavioral_evals, "MAX_SEED_ENTRIES", 8)
    else:
        (fixture_root / "cases" / "planning-happy" / "nested").mkdir()
        (fixture_root / "cases" / "planning-boundary" / "nested").mkdir()
        monkeypatch.setattr(behavioral_evals, "MAX_SEED_DIRECTORIES", 1)
    scratch_root = tmp_path / "scratch"

    with pytest.raises(EvaluationError) as raised:
        prepare_pilot(load_manifest(fixture_root / "manifest.json"), scratch_root)

    assert raised.value.code == "limit_exceeded"
    assert raised.value.field == expected_field
    assert not scratch_root.exists()


def test_prepare_rejects_total_copy_amplification_before_scratch_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    reads = 0
    real_read = behavioral_evals.read_regular_at

    def counting_read(parent_fd: int, name: str, *, max_bytes: int) -> bytes:
        nonlocal reads
        reads += 1
        return real_read(parent_fd, name, max_bytes=max_bytes)

    monkeypatch.setattr(behavioral_evals, "MAX_PILOT_COPY_BYTES", 1)
    monkeypatch.setattr(behavioral_evals, "read_regular_at", counting_read)
    scratch_root = tmp_path / "scratch"

    with pytest.raises(EvaluationError) as raised:
        prepare_pilot(manifest, scratch_root)

    assert raised.value.code == "limit_exceeded"
    assert raised.value.field == "pilot.copy_bytes"
    assert reads == 1
    assert not scratch_root.exists()


def test_prepare_rejects_changed_source_root_identity(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    manifest = load_manifest(fixture_root / "manifest.json")
    original_root = tmp_path / "original-fixtures"
    fixture_root.rename(original_root)
    shutil.copytree(original_root, fixture_root)
    scratch_root = tmp_path / "scratch"

    with pytest.raises(EvaluationError) as raised:
        prepare_pilot(manifest, scratch_root)

    assert raised.value.code == "unsafe_path"
    assert raised.value.field == "fixture_root"
    assert not scratch_root.exists()
