#!/usr/bin/env python3
"""Validate that a spec document carries every canonical section heading.

Checks a single ``docs/specs/<N>-<slug>.md`` file (or, once directory support
lands, every file in a ``docs/specs``-shaped directory) for the seven canonical
H2 headings: Context, Problem, Requirements, Acceptance Criteria,
Design Constraints, Out of Scope, Traceability. It exits non-zero and prints one
stderr line per missing heading. On success it prints ``OK`` and exits zero.

Run it against a single file or a directory:

    python scripts/spec-lint.py docs/specs/12-add-widget.md
    python scripts/spec-lint.py docs/specs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Kept in sync with solomon_harness.spec_doc.SECTION_HEADINGS by a cross-check
# test (this script cannot import that module: scripts run via
# `uv run python scripts/*.py` do not have solomon_harness on sys.path).
SECTION_HEADINGS = [
    "Context",
    "Problem",
    "Requirements",
    "Acceptance Criteria",
    "Design Constraints",
    "Out of Scope",
    "Traceability",
]

# The house template and the convention doc are not specs; they are excluded
# from directory scans (mirrors check-adr-unique.py's EXCLUDED set).
EXCLUDED = {"README.md", "0000-spec-template.md"}
FILENAME_RE = re.compile(r"^(\d+)-")


def check_file(path: Path) -> list[str]:
    """Return a list of problems found in path; an empty list means valid."""
    content = path.read_text(encoding="utf-8")
    lines = {line.strip() for line in content.splitlines()}
    errors: list[str] = []
    for heading in SECTION_HEADINGS:
        if f"## {heading}" not in lines:
            errors.append(f'{path.name}: missing required section "{heading}"')
    return errors


def check_directory(spec_dir: Path) -> list[str]:
    """Return a list of problems found across spec_dir; empty means valid.

    A malformed filename (no leading issue-number prefix) is reported and its
    section check is skipped, mirroring check-adr-unique.py's `continue` after
    a filename miss (no redundant double-report for the same file).
    """
    errors: list[str] = []
    for path in sorted(spec_dir.glob("*.md")):
        if path.name in EXCLUDED:
            continue
        if not FILENAME_RE.match(path.name):
            errors.append(f"{path.name}: filename does not start with an issue number")
            continue
        errors.extend(check_file(path))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check spec document(s) carry every canonical section heading."
    )
    parser.add_argument("path", help="A spec markdown file or a docs/specs-shaped directory.")
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"path not found: {path}", file=sys.stderr)
        return 2

    errors = check_directory(path) if path.is_dir() else check_file(path)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
