"""Tests for scripts/check-adr-unique.py.

The validator scans an ADR directory and fails when two ADRs share a number or
when a file's filename number disagrees with its H1 number. These tests drive it
through a subprocess so the exit code and messages are exercised exactly as a CI
hook would see them.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-adr-unique.py"


def _write_adr(dir_path: Path, name: str, number: str, title: str = "Title") -> None:
    (dir_path / name).write_text(
        f"# ADR-{number}: {title}\n\n- Status: accepted\n\n## Context\n\nBody.\n",
        encoding="utf-8",
    )


def _run(adr_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(adr_dir)],
        capture_output=True,
        text=True,
    )


def test_unique_adrs_pass(tmp_path):
    _write_adr(tmp_path, "0001-foo.md", "0001")
    _write_adr(tmp_path, "0002-bar.md", "0002")
    # The template and the index must be ignored, not validated.
    (tmp_path / "0000-adr-template.md").write_text(
        "# ADR-NNNN: <short decision title>\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Architecture Decision Records\n", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_duplicate_number_fails(tmp_path):
    _write_adr(tmp_path, "0001-foo.md", "0001")
    _write_adr(tmp_path, "0001-bar.md", "0001")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "duplicate ADR number 0001" in result.stderr


def test_filename_h1_mismatch_fails(tmp_path):
    # Filename says 0003 but the H1 says 0009.
    _write_adr(tmp_path, "0003-baz.md", "0009")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "does not match" in result.stderr
