"""Tests for scripts/check-adr-gate.py (#221 S2b, #235).

Every PR body must carry exactly one canonical ADR line. Driven through a
subprocess so exit codes and messages behave exactly as the CI step sees them.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-adr-gate.py"


def _run_body(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    body_file = tmp_path / "body.md"
    body_file.write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--body-file", str(body_file)],
        capture_output=True,
        text=True,
    )


def test_adr_link_passes(tmp_path):
    result = _run_body(tmp_path, "Summary...\n\nADR: docs/adrs/0029-install-documents-boundary.md\n")
    assert result.returncode == 0, result.stderr


def test_skip_with_reason_passes(tmp_path):
    result = _run_body(
        tmp_path,
        "Summary...\n\nADR: not warranted — prompt-text change inside an "
        "existing convention, no new dependency or contract.\n",
    )
    assert result.returncode == 0, result.stderr


def test_missing_line_fails(tmp_path):
    result = _run_body(tmp_path, "Summary with no decision statement.\n")
    assert result.returncode == 1
    assert "no ADR line" in result.stderr


def test_old_path_link_fails(tmp_path):
    result = _run_body(tmp_path, "ADR: docs/adr/0010-loop-single-driver-lock.md\n")
    assert result.returncode == 1
    assert "pre-migration" in result.stderr


def test_both_forms_fail_as_ambiguous(tmp_path):
    result = _run_body(
        tmp_path,
        "ADR: docs/adrs/0029-install-documents-boundary.md\n"
        "ADR: not warranted — also skipping.\n",
    )
    assert result.returncode == 1
    assert "one decision" in result.stderr


def test_bare_skip_without_reason_fails(tmp_path):
    result = _run_body(tmp_path, "ADR: not warranted\n")
    assert result.returncode == 1
    assert "reason" in result.stderr


def test_noncanonical_adr_line_fails(tmp_path):
    result = _run_body(tmp_path, "ADR: see the design doc\n")
    assert result.returncode == 1
    assert "neither canonical form" in result.stderr


def test_line_anywhere_in_a_long_body_passes(tmp_path):
    body = "\n".join(
        ["## Summary", "many lines...", "", "## Verification", "tests green", "",
         "ADR: not warranted — docs-only change.", "", "Closes #235"]
    )
    result = _run_body(tmp_path, body)
    assert result.returncode == 0, result.stderr


def test_env_source_and_missing_env_usage_error(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env", "PR_BODY"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 2
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "--env", "PR_BODY"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin",
             "PR_BODY": "ADR: not warranted — trivial.\n"},
    )
    assert ok.returncode == 0, ok.stderr
