#!/usr/bin/env python3
"""Fail when Ruff finds a new security issue on a changed production line.

Ruff evaluates the complete production package so its normal configuration and
``noqa`` handling remain authoritative.  Findings are then intersected with
lines added since ``--base-sha``.  Existing findings outside that diff remain a
visible migration backlog without blocking unrelated pull requests.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


PRODUCTION_ROOT = "solomon_harness"
_HUNK_RE = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@"
)


@dataclass(frozen=True)
class RuffFinding:
    """One normalized Ruff diagnostic."""

    path: str
    row: int
    column: int
    end_row: int
    code: str
    message: str


def parse_added_lines(patch: str) -> dict[str, frozenset[int]]:
    """Return new-file line numbers named by a zero-context unified diff."""

    current_path: str | None = None
    added: dict[str, set[int]] = {}
    for line in patch.splitlines():
        if line.startswith("+++ "):
            candidate = line[4:].split("\t", 1)[0]
            if candidate == "/dev/null":
                current_path = None
                continue
            current_path = candidate[2:] if candidate.startswith("b/") else candidate
            added.setdefault(current_path, set())
            continue

        match = _HUNK_RE.match(line)
        if current_path is None or match is None:
            continue
        start = int(match.group("start"))
        count_text = match.group("count")
        count = 1 if count_text is None else int(count_text)
        added[current_path].update(range(start, start + count))

    return {path: frozenset(lines) for path, lines in added.items() if lines}


def _relative_path(filename: str, repo_root: Path) -> str:
    path = Path(filename)
    if not path.is_absolute():
        path = repo_root / path
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Ruff reported a file outside the repository: {filename}") from exc


def parse_ruff_findings(output: str, repo_root: Path) -> tuple[RuffFinding, ...]:
    """Parse and validate Ruff's JSON output, failing closed on schema drift."""

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("Ruff JSON output is malformed") from exc
    if not isinstance(payload, list):
        raise ValueError("Ruff JSON output must be a list")

    findings: list[RuffFinding] = []
    for raw in payload:
        try:
            if not isinstance(raw, dict):
                raise TypeError
            location = raw["location"]
            end_location = raw["end_location"]
            if not isinstance(location, dict) or not isinstance(end_location, dict):
                raise TypeError
            filename = raw["filename"]
            code = raw["code"]
            message = raw["message"]
            row = location["row"]
            column = location["column"]
            end_row = end_location["row"]
            if not (
                isinstance(filename, str)
                and isinstance(code, str)
                and code.startswith("S")
                and isinstance(message, str)
                and isinstance(row, int)
                and isinstance(column, int)
                and isinstance(end_row, int)
                and 1 <= row <= end_row
            ):
                raise TypeError
        except (KeyError, TypeError) as exc:
            raise ValueError("Ruff JSON output has an unsupported finding schema") from exc
        findings.append(
            RuffFinding(
                path=_relative_path(filename, repo_root),
                row=row,
                column=column,
                end_row=end_row,
                code=code,
                message=message,
            )
        )
    return tuple(findings)


def filter_added_findings(
    findings: Sequence[RuffFinding],
    added_lines: Mapping[str, frozenset[int]],
) -> tuple[RuffFinding, ...]:
    """Select diagnostics whose source span intersects an added line."""

    selected = [
        finding
        for finding in findings
        if any(
            line in added_lines.get(finding.path, frozenset())
            for line in range(finding.row, finding.end_row + 1)
        )
    ]
    return tuple(
        sorted(selected, key=lambda item: (item.path, item.row, item.column, item.code))
    )


def _run(
    arguments: Sequence[str], repo_root: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments),
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_base_revision(base_sha: str, repo_root: Path) -> str:
    """Resolve a caller-provided ref to a commit before using it in ``git diff``."""

    if not base_sha.strip():
        raise ValueError("base revision cannot be empty")
    completed = _run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_sha}^{{commit}}",
        ],
        repo_root,
    )
    resolved = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", resolved):
        raise ValueError(f"cannot resolve base revision: {base_sha}")
    return resolved


def changed_production_lines(base_sha: str, repo_root: Path) -> dict[str, frozenset[int]]:
    """Collect tracked diff lines and complete untracked Python files."""

    resolved = resolve_base_revision(base_sha, repo_root)
    completed = _run(
        [
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            resolved,
            "--",
            PRODUCTION_ROOT,
        ],
        repo_root,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "git diff failed"
        raise RuntimeError(detail)
    added = {path: set(lines) for path, lines in parse_added_lines(completed.stdout).items()}

    untracked = _run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            PRODUCTION_ROOT,
        ],
        repo_root,
    )
    if untracked.returncode != 0:
        detail = untracked.stderr.strip() or "git ls-files failed"
        raise RuntimeError(detail)
    for relative in untracked.stdout.splitlines():
        path = repo_root / relative
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"cannot read untracked production file: {relative}") from exc
        added.setdefault(relative, set()).update(range(1, line_count + 1))

    return {path: frozenset(lines) for path, lines in added.items() if lines}


def run_ruff(repo_root: Path) -> tuple[RuffFinding, ...]:
    """Run Ruff's security family while retaining its normal ``noqa`` behavior."""

    completed = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "S",
            "--output-format",
            "json",
            PRODUCTION_ROOT,
        ],
        repo_root,
    )
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or "Ruff security scan failed"
        raise RuntimeError(detail)
    return parse_ruff_findings(completed.stdout, repo_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-sha",
        required=True,
        help="Git commit/ref used as the baseline for added production lines",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        added_lines = changed_production_lines(args.base_sha, repo_root)
        if not added_lines:
            print("Security diff gate passed: no changed production lines.")
            return 0
        findings = filter_added_findings(run_ruff(repo_root), added_lines)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Security diff gate error: {exc}", file=sys.stderr)
        return 2

    if findings:
        print("Security diff gate failed: new Ruff S findings:", file=sys.stderr)
        for finding in findings:
            print(
                f"{finding.path}:{finding.row}:{finding.column}: "
                f"{finding.code} {finding.message}",
                file=sys.stderr,
            )
        return 1

    line_count = sum(len(lines) for lines in added_lines.values())
    print(
        "Security diff gate passed: no new Ruff S findings on "
        f"{line_count} changed production line(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
