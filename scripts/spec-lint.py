#!/usr/bin/env python3
"""Validate that a spec document carries every canonical section heading.

Checks a single ``docs/specs/<N>-<slug>.md`` file (or, once directory support
lands, every file in a ``docs/specs``-shaped directory) for the seven canonical
H2 headings: Context, Problem, Requirements, Acceptance Criteria,
Design Constraints, Out of Scope, Traceability, in that canonical order and
each appearing at most once. It exits non-zero and prints one stderr line per
missing, duplicated, or out-of-order heading. On success it prints ``OK`` and
exits zero.

Run it against a single file or a directory (the path defaults to
``docs/specs``, mirroring ``scripts/check-adr-unique.py``'s zero-arg
convention):

    python scripts/spec-lint.py docs/specs/12-add-widget.md
    python scripts/spec-lint.py docs/specs
    python scripts/spec-lint.py
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
HEADING_RE = re.compile(r"^##\s+(.*\S)\s*$")


def _document_headings(content: str) -> list[str]:
    """Return every `## ` heading's text, in document order (as written)."""
    headings = []
    for line in content.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            headings.append(match.group(1))
    return headings


def check_file(path: Path) -> list[str]:
    """Return a list of problems found in path; an empty list means valid.

    Presence alone is not enough: a document could carry all seven canonical
    headings scrambled or repeated and still pass a presence-only check, which
    would also blind the lint to a heading-injection attack (see
    solomon_harness.spec_doc.render_spec's title/adr_ref sanitization) landing
    a forged duplicate heading. So this checks, in order: every canonical
    heading is present; none is duplicated; and the ones present appear in
    canonical relative order.
    """
    content = path.read_text(encoding="utf-8")
    headings = _document_headings(content)
    canonical = set(SECTION_HEADINGS)
    canonical_found = [heading for heading in headings if heading in canonical]

    counts: dict[str, int] = {}
    for heading in canonical_found:
        counts[heading] = counts.get(heading, 0) + 1

    errors: list[str] = []
    for heading in SECTION_HEADINGS:
        if heading not in counts:
            errors.append(f'{path.name}: missing required section "{heading}"')
    for heading in SECTION_HEADINGS:
        if counts.get(heading, 0) > 1:
            errors.append(f'{path.name}: duplicate section "{heading}"')

    if not errors:
        # All seven present exactly once: first_seen_order is a permutation
        # of SECTION_HEADINGS, so the first mismatch against the canonical
        # order pinpoints exactly where the document went out of order.
        seen: set[str] = set()
        first_seen_order: list[str] = []
        for heading in canonical_found:
            if heading not in seen:
                first_seen_order.append(heading)
                seen.add(heading)
        for actual, expected in zip(first_seen_order, SECTION_HEADINGS):
            if actual != expected:
                errors.append(
                    f'{path.name}: section "{actual}" is out of order '
                    f'(expected "{expected}" at this position)'
                )
                break

    return errors


def check_directory(spec_dir: Path) -> list[str]:
    """Return a list of problems found across spec_dir; empty means valid.

    A malformed filename (no leading issue-number prefix) is reported and its
    section check is skipped, mirroring check-adr-unique.py's `continue` after
    a filename miss (no redundant double-report for the same file). A symlink
    is skipped outright (not read, not reported) so the scan can never be
    tricked into following a link out of docs/specs.
    """
    errors: list[str] = []
    for path in sorted(spec_dir.glob("*.md")):
        if path.is_symlink():
            continue
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
    default_dir = Path(__file__).resolve().parent.parent / "docs" / "specs"
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default_dir),
        help="A spec markdown file or a docs/specs-shaped directory (default: docs/specs).",
    )
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
