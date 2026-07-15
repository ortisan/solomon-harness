"""Tests for the incremental Ruff security gate.

The gate intentionally evaluates all Ruff ``S`` findings but reports only
findings whose source span intersects a production line added since the chosen
base commit.  This lets CI enforce new security work without grandfathered
findings making the legacy baseline unactionable.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-security-diff.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_security_diff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _finding(
    path: str,
    row: int,
    *,
    end_row: int | None = None,
    code: str = "S105",
) -> dict[str, object]:
    return {
        "code": code,
        "filename": path,
        "location": {"row": row, "column": 5},
        "end_location": {"row": end_row or row, "column": 20},
        "message": "Possible hardcoded password",
    }


def test_parse_added_lines_handles_multiple_hunks_and_new_files() -> None:
    gate = _load_script()
    patch = """\
diff --git a/solomon_harness/alpha.py b/solomon_harness/alpha.py
--- a/solomon_harness/alpha.py
+++ b/solomon_harness/alpha.py
@@ -2,0 +3,2 @@
+first = 1
+second = 2
@@ -20 +22,0 @@
-removed = True
@@ -30 +31 @@
-old = 1
+new = 2
diff --git a/solomon_harness/new.py b/solomon_harness/new.py
--- /dev/null
+++ b/solomon_harness/new.py
@@ -0,0 +1,3 @@
+one = 1
+two = 2
+three = 3
"""

    assert gate.parse_added_lines(patch) == {
        "solomon_harness/alpha.py": frozenset({3, 4, 31}),
        "solomon_harness/new.py": frozenset({1, 2, 3}),
    }


def test_filter_reports_only_findings_intersecting_added_production_lines(
    tmp_path: Path,
) -> None:
    gate = _load_script()
    findings = gate.parse_ruff_findings(
        json.dumps(
            [
                _finding(str(tmp_path / "solomon_harness" / "changed.py"), 8),
                _finding(
                    str(tmp_path / "solomon_harness" / "changed.py"),
                    10,
                    end_row=12,
                    code="S603",
                ),
                _finding(str(tmp_path / "solomon_harness" / "changed.py"), 30),
                _finding(str(tmp_path / "tests" / "test_changed.py"), 8),
            ]
        ),
        tmp_path,
    )
    added = {"solomon_harness/changed.py": frozenset({8, 11})}

    selected = gate.filter_added_findings(findings, added)

    assert [(finding.code, finding.row) for finding in selected] == [
        ("S105", 8),
        ("S603", 10),
    ]


def test_parse_ruff_findings_rejects_malformed_json(tmp_path: Path) -> None:
    gate = _load_script()

    try:
        gate.parse_ruff_findings("not-json", tmp_path)
    except ValueError as exc:
        assert "Ruff JSON" in str(exc)
    else:
        raise AssertionError("malformed Ruff output must fail closed")


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _security_repo(tmp_path: Path) -> tuple[Path, str]:
    package = tmp_path / "solomon_harness"
    package.mkdir()
    target = package / "example.py"
    target.write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Security Gate Test")
    _git(tmp_path, "config", "user.email", "security-gate@example.invalid")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    base = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return target, base


def _run_gate(repo: Path, base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--base-sha",
            base,
        ],
        capture_output=True,
        text=True,
    )


def test_cli_fails_for_new_security_finding_and_respects_justified_noqa(
    tmp_path: Path,
) -> None:
    target, base = _security_repo(tmp_path)
    target.write_text('value = 1\npassword = "secret"\n', encoding="utf-8")

    failed = _run_gate(tmp_path, base)

    assert failed.returncode == 1
    assert "example.py:2" in failed.stderr
    assert "S105" in failed.stderr

    target.write_text(
        'value = 1\npassword = "secret"  # noqa: S105 - non-secret test sentinel\n',
        encoding="utf-8",
    )
    allowed = _run_gate(tmp_path, base)

    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "no new Ruff S findings" in allowed.stdout


def test_cli_ignores_a_legacy_finding_on_an_unchanged_line(tmp_path: Path) -> None:
    target, base = _security_repo(tmp_path)
    target.write_text('password = "legacy"\nvalue = 1\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "legacy finding")
    base = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target.write_text('password = "legacy"\nvalue = 2\n', encoding="utf-8")

    result = _run_gate(tmp_path, base)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no new Ruff S findings" in result.stdout


def test_cli_rejects_an_unknown_base_revision(tmp_path: Path) -> None:
    _security_repo(tmp_path)

    result = _run_gate(tmp_path, "not-a-revision")

    assert result.returncode == 2
    assert "cannot resolve base revision" in result.stderr


def test_ci_supplies_full_history_and_the_event_specific_base_revision() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "fetch-depth: 0" in workflow
    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "PUSH_BASE_SHA: ${{ github.event.before }}" in workflow
    assert 'base_sha="$PR_BASE_SHA"' in workflow
    assert 'base_sha="$PUSH_BASE_SHA"' in workflow
    assert (
        'uv run python scripts/check-security-diff.py --base-sha "$base_sha"'
        in workflow
    )
