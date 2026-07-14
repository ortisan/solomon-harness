#!/usr/bin/env python3
"""Validate the house spec documents under ``docs/specs`` (#221 S1).

Every spec is ``<N>-<slug>.md`` (a plain issue number, a kebab-case slug) and
must carry the nine mandated sections: Context, Problem, Requirements,
Implementation Pointers, Acceptance Criteria, Verification, Design Constraints,
Out of Scope, and Traceability. A section may hold the explicit placeholder
``TBD (refine)`` but never be empty, and Traceability must cite the filename's
issue number (``#<N>``). The template and the README index are ignored. A
missing specs directory is valid (nothing to lint yet).

Implementation-ready bar (maintainer directive 2026-07-14): once a spec is
marked ``Status: ready`` or ``Status: implemented``, no section may still hold
the ``TBD (refine)`` placeholder. Refinement resolves every section — exact
``file:line`` pointers, the concrete approach, and the verification command —
so the implementing model never has to guess. A ``draft`` spec may still carry
placeholders.

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
# The issue number carries no leading zeros, so the accepted filename form and
# the required Traceability citation ("#<N>") are always the same string.
FILENAME_RE = re.compile(r"^([1-9][0-9]*)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
# A spec is prose; anything beyond this is not a spec (guards CI memory/time).
MAX_SPEC_BYTES = 256 * 1024
REQUIRED_SECTIONS = (
    "## Context",
    "## Problem",
    "## Requirements",
    "## Implementation Pointers",
    "## Acceptance Criteria",
    "## Verification",
    "## Design Constraints",
    "## Out of Scope",
    "## Traceability",
)
# The implementation-ready bar: a spec at these statuses must carry no
# unresolved placeholder — refinement leaves nothing for the implementer to
# guess. Detection is deliberately tolerant so the gate fails closed, not open:
# a placeholder is caught under a leading list marker and across case/spacing
# variants, and on a prefix ("TBD (refine) — blocked on X"), while a line that
# merely quotes the phrase mid-sentence is not flagged. Status is read from the
# header's "- Issue: #N · Status:" line specifically so neither a body mention
# nor an earlier changelog note in the header can shadow it, tolerating
# bold/code-span markup so a formatted header does not silently disable the gate.
TBD_PLACEHOLDER = "TBD (refine)"
_PLACEHOLDER_KEYS = ("tbd(refine)", "todo", "fixme", "tbd")
COMPLETION_GATED_STATUSES = {"ready", "implemented"}
VALID_STATUSES = {"draft", "ready", "implemented", "superseded"}
CANONICAL_LINE_RE = re.compile(
    r"^\s*-\s*Issue:\s*#([1-9][0-9]*)\s*·\s*Status:\s*([A-Za-z0-9_-]+)"
)


def _spec_status(text: str) -> tuple[str | None, str | None]:
    """The spec's lowercased Status token and status issue number, or (None, None).

    The status lives on the header's ``- Issue: #N · Status: <token>`` line.
    It is read from that line specifically — not the leftmost "Status:" in the
    header blob — so an earlier changelog note or quoted old header ("Migrated
    from Status: draft ...") cannot shadow the real value. Markup around the
    label and value (``**Status:**``, ``Status: `ready```) is tolerated.
    """
    header = text.split("\n## ", 1)[0]
    for line in header.splitlines():
        clean = line.replace("*", "").replace("`", "")
        match = CANONICAL_LINE_RE.match(clean)
        if match:
            return match.group(2).lower(), match.group(1)
    return None, None


def _is_unresolved_placeholder(line: str) -> bool:
    """True when a line contains an unresolved placeholder key.

    Catches common placeholders like TBD (refine), TODO, FIXME, TBD, and empty
    markdown checkboxes [ ] at the start of a list item or line.
    """
    # Check for empty checkboxes like "[ ]", "- [ ]", etc.
    collapsed_checkbox = re.sub(r"\s+", "", line)
    if collapsed_checkbox.startswith("-[]") or collapsed_checkbox.startswith("[]") or collapsed_checkbox.startswith("*[]"):
        return True

    collapsed = re.sub(r"\s+", "", line).casefold()
    collapsed = re.sub(r"^[^a-z]+", "", collapsed)
    for key in _PLACEHOLDER_KEYS:
        if collapsed.startswith(key):
            suffix = collapsed[len(key):]
            if not suffix or not suffix[0].isalnum():
                return True
    return False


def _sections(text: str) -> tuple[dict[str, str], list[str]]:
    """Map each ``## `` heading to its body text, plus any duplicated headings.

    A duplicated heading would silently shadow the first occurrence's body, so
    it is reported as a defect instead of validated last-one-wins.
    """
    result: dict[str, str] = {}
    duplicates: list[str] = []
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                result[current] = "\n".join(body)
            current = line.strip()
            if current in result:
                duplicates.append(current)
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        result[current] = "\n".join(body)
    return result, duplicates


def check_spec(path: Path) -> list[str]:
    """Return the list of defects for one spec file (empty == passes)."""
    gaps: list[str] = []
    match = FILENAME_RE.match(path.name)
    if not match:
        return [
            f"{path}: filename must be <issue-number>-<kebab-slug>.md "
            f"(lowercase, hyphens, no leading zeros), got '{path.name}'"
        ]
    # Read the file first and check the size of the read text to prevent TOCTOU race
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > MAX_SPEC_BYTES:
        return [f"{path}: larger than {MAX_SPEC_BYTES} bytes — not a spec"]
    issue_number = match.group(1)
    sections, duplicates = _sections(text)
    for heading in duplicates:
        gaps.append(f"{path}: duplicated section heading '{heading}'")
    for heading in REQUIRED_SECTIONS:
        if heading not in sections:
            gaps.append(f"{path}: missing required section '{heading}'")
        elif not sections[heading].strip():
            gaps.append(
                f"{path}: section '{heading}' is empty — carry content or the "
                f"explicit placeholder 'TBD (refine)'"
            )
    status, status_issue = _spec_status(text)
    if status is None:
        gaps.append(
            f"{path}: header must carry a parseable 'Status:' line "
            f"(draft | ready | implemented | superseded)"
        )
    elif status not in VALID_STATUSES:
        gaps.append(
            f"{path}: header carries an invalid status '{status}' — must be one of "
            f"(draft | ready | implemented | superseded)"
        )
    else:
        if status_issue != issue_number:
            gaps.append(
                f"{path}: status line issue number '#{status_issue}' must match "
                f"filename issue number '#{issue_number}'"
            )
        if status in COMPLETION_GATED_STATUSES:
            for heading, body in sections.items():
                if any(_is_unresolved_placeholder(line) for line in body.splitlines()):
                    gaps.append(
                        f"{path}: section '{heading}' still holds an unresolved "
                        f"'{TBD_PLACEHOLDER}' but the spec is marked Status: "
                        f"{status} — resolve every section before Ready"
                    )
    traceability = sections.get("## Traceability", "")
    if "## Traceability" in sections and not re.search(
        rf"#{issue_number}\b", traceability
    ):
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
