"""Tests for scripts/spec-lint.py (#221 S1).

The validator enforces the house spec convention: <N>-<slug>.md filenames,
the seven mandated sections, no empty section (the explicit 'TBD (refine)'
placeholder is content), and Traceability citing the filename's issue number.
Driven through a subprocess so the exit codes and messages are exercised
exactly as CI sees them.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "spec-lint.py"

VALID_SPEC = """# Spec 42: add csv export

- Issue: #42 · Status: draft

## Context

Elicitation: skipped — all 6 readiness criteria met.

## Problem

Users cannot export reports.

## Requirements

1. Export completes in under 5 s for 10k rows.

## Acceptance Criteria

Scenario: happy path export.

## Design Constraints

TBD (refine)

## Out of Scope

Scheduled exports.

## Traceability

- Issue: #42
- ADR: none yet
"""


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )


def test_valid_spec_passes(tmp_path):
    (tmp_path / "42-add-csv-export.md").write_text(VALID_SPEC, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_template_and_readme_are_excluded(tmp_path):
    (tmp_path / "0000-spec-template.md").write_text("# Spec <N>\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Spec-driven issue documents\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_missing_section_fails_naming_it(tmp_path):
    body = VALID_SPEC.replace("## Traceability\n\n- Issue: #42\n- ADR: none yet\n", "")
    (tmp_path / "42-add-csv-export.md").write_text(body, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing required section '## Traceability'" in result.stderr


def test_empty_section_fails_unless_placeholder(tmp_path):
    body = VALID_SPEC.replace(
        "## Design Constraints\n\nTBD (refine)\n", "## Design Constraints\n\n"
    )
    (tmp_path / "42-add-csv-export.md").write_text(body, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "'## Design Constraints' is empty" in result.stderr


def test_malformed_filename_fails_naming_the_rule(tmp_path):
    (tmp_path / "Add_CSV_Export.md").write_text(VALID_SPEC, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "filename must be <issue-number>-<kebab-slug>.md" in result.stderr


def test_traceability_must_cite_the_filename_issue_number(tmp_path):
    body = VALID_SPEC.replace("- Issue: #42\n", "- Issue: #99\n")
    body = body.replace("# Spec 42", "# Spec 42 (mismatched)")
    (tmp_path / "42-add-csv-export.md").write_text(body, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "must cite the filename's issue number '#42'" in result.stderr


def test_single_file_argument_is_linted(tmp_path):
    spec = tmp_path / "42-add-csv-export.md"
    spec.write_text(VALID_SPEC, encoding="utf-8")
    result = _run(spec)
    assert result.returncode == 0, result.stderr


def test_duplicated_heading_is_a_named_defect(tmp_path):
    body = VALID_SPEC + "\n## Problem\n\nA second problem section.\n"
    (tmp_path / "42-add-csv-export.md").write_text(body, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "duplicated section heading '## Problem'" in result.stderr


def test_leading_zero_filename_is_rejected(tmp_path):
    (tmp_path / "042-add-csv-export.md").write_text(VALID_SPEC, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "no leading zeros" in result.stderr


def test_traceability_superstring_does_not_satisfy_the_citation(tmp_path):
    # "#423" must not satisfy the required "#42" citation.
    body = VALID_SPEC.replace("- Issue: #42\n", "- Issue: #423\n")
    (tmp_path / "42-add-csv-export.md").write_text(body, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "must cite the filename's issue number '#42'" in result.stderr


def test_oversized_file_is_rejected_without_reading(tmp_path):
    (tmp_path / "42-add-csv-export.md").write_text(
        VALID_SPEC + "x" * (256 * 1024), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "not a spec" in result.stderr


def test_missing_specs_directory_is_valid(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "nothing to lint" in result.stdout
