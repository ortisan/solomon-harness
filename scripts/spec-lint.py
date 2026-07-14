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
# Normalized placeholder key: lowercase, whitespace removed, so "TBD (refine)",
# "tbd(refine)", and "- TBD (Refine)" all reduce to this.
_PLACEHOLDER_KEY = "tbd(refine)"
COMPLETION_GATED_STATUSES = {"ready", "implemented"}
STATUS_RE = re.compile(r"Status:\s*([A-Za-z]+)")


def _spec_status(text: str) -> str | None:
    """The spec's lowercased Status token, or None when the header lacks one.

    The status lives on the header's ``- Issue: #N · Status: <token>`` line.
    It is read from that line specifically — not the leftmost "Status:" in the
    header blob — so an earlier changelog note or quoted old header ("Migrated
    from Status: draft ...") cannot shadow the real value. Markup around the
    label and value (``**Status:**``, ``Status: `ready```) is tolerated, and
    the last match on the line wins so a same-line aside cannot shadow the
    trailing canonical token.
    """
    header = text.split("\n## ", 1)[0]
    for line in header.splitlines():
        clean = line.replace("*", "").replace("`", "")
        if "Issue:" in clean and "Status:" in clean:
            matches = STATUS_RE.findall(clean)
            if matches:
                return matches[-1].lower()
    return None


def _is_unresolved_placeholder(line: str) -> bool:
    """True when a line is an unresolved ``TBD (refine)`` placeholder.

    The line is reduced to a bare token — whitespace removed, casefolded, and
    any leading run of non-alphanumeric characters (list markers, quotes,
    brackets, backticks, emphasis) stripped — then matched on a prefix. So
    ``- `TBD (refine)```, ``[TBD (refine)]``, and ``TBD (refine) — blocked`` are
    all caught, while a sentence that merely quotes the phrase mid-text is not
    (it does not start with the token).
    """
    collapsed = re.sub(r"\s+", "", line).casefold()
    collapsed = re.sub(r"^[^a-z0-9]+", "", collapsed)
    return collapsed.startswith(_PLACEHOLDER_KEY)


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
    if path.stat().st_size > MAX_SPEC_BYTES:
        return [f"{path}: larger than {MAX_SPEC_BYTES} bytes — not a spec"]
    issue_number = match.group(1)
    text = path.read_text(encoding="utf-8")
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
    status = _spec_status(text)
    if status is None:
        gaps.append(
            f"{path}: header must carry a parseable 'Status:' line "
            f"(draft | ready | implemented | superseded)"
        )
    elif status in COMPLETION_GATED_STATUSES:
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
