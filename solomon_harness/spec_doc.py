"""Generate a structured spec document (docs/specs/<N>-<slug>.md) per issue.

Pure functions here map an issue's rendered GitHub body onto the house spec
template's seven canonical headings (Context, Problem, Requirements,
Acceptance Criteria, Design Constraints, Out of Scope, Traceability). They are
invoked by /solomon-issue's issue-creation step so the mapping and the
filesystem write are unit-testable without an LLM turn.

CLI:
    python -m solomon_harness.spec_doc generate --issue N --title "<title>" \
        --body-file <path> [--adr "<ADR text>"]
"""

from __future__ import annotations

import re
import unicodedata

# The seven canonical headings, in the order they must appear. Kept in sync
# with scripts/spec-lint.py's SECTION_HEADINGS by a cross-check test (that
# script cannot import this module: it runs via `uv run python scripts/*.py`,
# which does not put solomon_harness on sys.path).
SECTION_HEADINGS = [
    "Context",
    "Problem",
    "Requirements",
    "Acceptance Criteria",
    "Design Constraints",
    "Out of Scope",
    "Traceability",
]

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")


def slugify(title: str) -> str:
    """Return an ASCII kebab-case slug safe to embed in a filesystem path.

    Strips diacritics via NFKD normalization, then replaces every run of
    non-alphanumeric characters (including path separators `/`, `\\` and `.`)
    with a single dash, so no path-traversal sequence can survive into the
    result (STRIDE: Tampering). An all-symbol title collapses to the empty
    string, which falls back to the fixed slug "untitled" rather than an
    empty or colliding filename.
    """
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("-", normalized.lower()).strip("-")
    return slug or "untitled"


def spec_filename(issue_number: int, title: str) -> str:
    """Return the spec's filename: '<issue_number>-<slug(title)>.md'."""
    return f"{issue_number}-{slugify(title)}.md"


def parse_issue_sections(body: str) -> dict[str, str]:
    """Split a `## `-delimited issue body into a heading-keyed dict.

    Keys are the heading text, lowercased (so lookups are case-insensitive).
    Values are the section's body text, stripped. Any preamble before the
    first `## ` heading is discarded. A body with no `## ` heading at all
    returns an empty dict rather than raising.
    """
    sections: dict[str, str] = {}
    heading: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        match = _H2_RE.match(line)
        if match:
            if heading is not None:
                sections[heading] = "\n".join(lines).strip()
            heading = match.group(1).strip().lower()
            lines = []
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        sections[heading] = "\n".join(lines).strip()
    return sections
