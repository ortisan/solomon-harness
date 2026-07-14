"""Tests for scripts/spec-lint.py.

The validator checks that a spec document (``docs/specs/<N>-<slug>.md``) carries
all seven canonical headings, and that a directory of spec documents has
well-formed filenames. It mirrors ``scripts/check-adr-unique.py``'s shape: run
through a subprocess so the exit code and stderr are exercised exactly as CI
would see them.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "spec-lint.py"

SECTION_HEADINGS = [
    "Context",
    "Problem",
    "Requirements",
    "Acceptance Criteria",
    "Design Constraints",
    "Out of Scope",
    "Traceability",
]


def _write_spec(path: Path, omit: str | None = None) -> None:
    lines = ["# Spec: Title\n\n"]
    for heading in SECTION_HEADINGS:
        if heading == omit:
            continue
        lines.append(f"## {heading}\n\nBody text.\n\n")
    path.write_text("".join(lines), encoding="utf-8")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_single_file_missing_section_fails(tmp_path):
    spec = tmp_path / "1-a-title.md"
    _write_spec(spec, omit="Design Constraints")

    result = _run(str(spec))

    assert result.returncode == 1
    assert (
        result.stderr.strip()
        == f'{spec.name}: missing required section "Design Constraints"'
    )


def test_single_file_all_sections_pass(tmp_path):
    spec = tmp_path / "1-a-title.md"
    _write_spec(spec)

    result = _run(str(spec))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
