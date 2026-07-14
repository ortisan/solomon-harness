#!/usr/bin/env python3
"""Validate the house spec documents under ``docs/specs`` (#221 S1).

Every spec is ``<N>-<slug>.md`` (a plain issue number, a kebab-case slug) and
must carry the seven mandated sections: Context, Problem, Requirements,
Acceptance Criteria, Design Constraints, Out of Scope, and Traceability. A
section may hold the explicit placeholder ``TBD (refine)`` but never be empty,
and Traceability must cite the filename's issue number (``#<N>``). The
template and the README index are ignored. A missing specs directory is valid
(nothing to lint yet).

Run it from the repository root, point it at a directory, or lint one file:

    python scripts/spec-lint.py
    python scripts/spec-lint.py path/to/specs
    python scripts/spec-lint.py docs/specs/233-spec-per-issue-docs.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXCLUDED = {"README.md", "0000-spec-template.md"}
FILENAME_RE = re.compile(r"^([0-9]+)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
REQUIRED_SECTIONS = (
    "## Context",
    "## Problem",
    "## Requirements",
    "## Acceptance Criteria",
    "## Design Constraints",
    "## Out of Scope",
    "## Traceability",
)


def _sections(text: str) -> dict[str, str]:
    """Map each ``## `` heading to its body text (up to the next heading)."""
    result: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                result[current] = "\n".join(body)
            current = line.strip()
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        result[current] = "\n".join(body)
    return result


def check_spec(path: Path) -> list[str]:
    """Return the list of defects for one spec file (empty == passes)."""
    gaps: list[str] = []
    match = FILENAME_RE.match(path.name)
    if not match:
        return [
            f"{path}: filename must be <issue-number>-<kebab-slug>.md "
            f"(lowercase, hyphens), got '{path.name}'"
        ]
    issue_number = str(int(match.group(1)))
    sections = _sections(path.read_text(encoding="utf-8"))
    for heading in REQUIRED_SECTIONS:
        if heading not in sections:
            gaps.append(f"{path}: missing required section '{heading}'")
        elif not sections[heading].strip():
            gaps.append(
                f"{path}: section '{heading}' is empty — carry content or the "
                f"explicit placeholder 'TBD (refine)'"
            )
    traceability = sections.get("## Traceability", "")
    if "## Traceability" in sections and f"#{issue_number}" not in traceability:
        gaps.append(
            f"{path}: Traceability must cite the filename's issue number "
            f"'#{issue_number}'"
        )
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Spec files or a specs directory (default: docs/specs)",
    )
    args = parser.parse_args()

    targets: list[Path] = []
    if args.paths:
        for raw in args.paths:
            path = Path(raw)
            if path.is_dir():
                targets.extend(sorted(path.glob("*.md")))
            else:
                targets.append(path)
    else:
        specs_dir = Path("docs") / "specs"
        if not specs_dir.is_dir():
            print("OK  no docs/specs directory yet; nothing to lint")
            return 0
        targets = sorted(specs_dir.glob("*.md"))

    gaps: list[str] = []
    checked = 0
    for path in targets:
        if path.name in EXCLUDED:
            continue
        if not path.is_file():
            gaps.append(f"{path}: file not found")
            continue
        checked += 1
        gaps.extend(check_spec(path))

    if gaps:
        for gap in gaps:
            print(gap, file=sys.stderr)
        return 1
    print(f"OK  {checked} spec(s) meet the house template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
