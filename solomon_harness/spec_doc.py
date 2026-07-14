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

import argparse
import re
import sys
import unicodedata
from pathlib import Path

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

# /solomon-issue does not render "In scope"/"Out of scope" as their own `## `
# headings; they are plain lines (optionally followed by a colon and a
# parenthetical, e.g. "Out of scope (and why):") nested inside the "## Scope"
# section. This strips both before comparing against a sub-block label.
_SCOPE_LABEL_TRAILER_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Maps each canonical heading onto the issue-body section key (as produced by
# parse_issue_sections, already lowercased) that supplies its content. Scope's
# "In scope"/"Out of scope" sub-blocks and Traceability are handled separately
# since they are not literal 1:1 section lookups (see Proposed change in
# PLAN.md for the full rationale).
_DIRECT_SECTION_MAP = {
    "Context": "user story",
    "Problem": "problem statement",
    "Acceptance Criteria": "acceptance criteria",
    "Design Constraints": "definition of ready",
}

# Placeholder for a section the issue body did not supply derivable content
# for (the Boundary scenario: a minimal issue still yields a complete spec).
# Traceability never falls back to this: it is always synthesized.
TBD_PLACEHOLDER = "TBD (refine)"

# Filesystem-safety cap on the slug (STRIDE: Denial of Service via an
# unbounded filename -- an issue title of a few hundred characters used to
# turn into a filename long enough to trip a filesystem's name-length limit,
# raising a raw OSError out of write_spec).
_MAX_SLUG_LENGTH = 80


def slugify(title: str) -> str:
    """Return an ASCII kebab-case slug safe to embed in a filesystem path.

    Strips diacritics via NFKD normalization, then replaces every run of
    non-alphanumeric characters (including path separators `/`, `\\` and `.`)
    with a single dash, so no path-traversal sequence can survive into the
    result (STRIDE: Tampering). An all-symbol title collapses to the empty
    string, which falls back to the fixed slug "untitled" rather than an
    empty or colliding filename. The result is capped at `_MAX_SLUG_LENGTH`
    characters, with any dash left dangling by the cut stripped off, so a very
    long title cannot produce an unwieldy or filesystem-hostile filename.
    """
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("-", normalized.lower()).strip("-")
    slug = slug[:_MAX_SLUG_LENGTH].rstrip("-")
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


def _normalized_label(line: str) -> str:
    """Fold a scope sub-block label line to a bare comparison key.

    "Out of scope (and why):" -> "out of scope"; "In scope:" -> "in scope".
    The trailing colon is stripped before the parenthetical, since the
    parenthetical (when present) sits between the label and the colon.
    """
    stripped = line.strip().rstrip(":").strip()
    stripped = _SCOPE_LABEL_TRAILER_RE.sub("", stripped).strip()
    return stripped.lower()


def _scope_subsection(scope_text: str, label: str) -> str | None:
    """Return the bullet content under a scope sub-block label, or None.

    The "## Scope" section nests "In scope"/"Out of scope" as plain label
    lines rather than their own `## ` headings (see the module docstring), so
    this scans line by line for a label match, then collects every following
    line up to the next recognized label or the end of the section.
    """
    lines = scope_text.splitlines()
    label_key = label.lower()
    start = None
    for i, line in enumerate(lines):
        if _normalized_label(line) == label_key:
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start, len(lines)):
        candidate = _normalized_label(lines[j])
        if candidate.endswith("scope") and candidate != label_key:
            end = j
            break

    content = "\n".join(lines[start:end]).strip()
    return content or None


def _sanitize_inline(value: str) -> str:
    """Collapse a caller-supplied value to a single safe line.

    Folds every run of whitespace (including embedded newlines) to a single
    space, then strips any leading `#` characters. Without this, a `title` or
    `adr_ref` containing a line like "## Traceability" would, once
    interpolated verbatim, forge an extra canonical-looking `## ` heading line
    in the rendered document (a Markdown-heading-injection: STRIDE Tampering).
    Collapsing to one line means the value can never itself start a new
    physical line, so it can never be mistaken for a heading by a downstream
    parser such as scripts/spec-lint.py.
    """
    return " ".join(value.split()).lstrip("#").strip()


def render_spec(
    issue_number: int,
    title: str,
    body: str,
    adr_ref: str | None = None,
) -> str:
    """Render the full spec document markdown for one issue.

    Maps the issue body's sections onto the seven canonical headings per the
    mapping table in PLAN.md's Proposed change, and synthesizes Traceability
    (never derived from the body) as "Issue: #<N>" plus either the supplied
    `adr_ref` verbatim or the literal "No related ADR" when none is given.
    `title` and `adr_ref` are sanitized (see `_sanitize_inline`) before
    interpolation, since both are caller-controlled strings. Emits the
    template's front-matter block (`- Issue: #<N>` / `- Status: draft`)
    right under the `# Spec: <title>` heading, above the `## ` sections.
    """
    title = _sanitize_inline(title)
    sections = parse_issue_sections(body)
    scope_text = sections.get("scope", "")

    content_by_heading: dict[str, str | None] = {
        heading: sections.get(key) for heading, key in _DIRECT_SECTION_MAP.items()
    }
    content_by_heading["Requirements"] = _scope_subsection(scope_text, "in scope")
    content_by_heading["Out of Scope"] = _scope_subsection(scope_text, "out of scope")
    content_by_heading["Traceability"] = (
        f"Issue: #{issue_number}\n"
        f"{_sanitize_inline(adr_ref) if adr_ref else 'No related ADR'}"
    )

    parts = [
        f"# Spec: {title}\n",
        f"- Issue: #{issue_number}\n- Status: draft\n",
    ]
    for heading in SECTION_HEADINGS:
        content = content_by_heading.get(heading) or TBD_PLACEHOLDER
        parts.append(f"## {heading}\n\n{content}\n")
    return "\n".join(parts) + "\n"


def write_spec(
    root: Path,
    issue_number: int,
    title: str,
    body: str,
    adr_ref: str | None = None,
) -> Path:
    """Render and write docs/specs/<issue_number>-<slug(title)>.md under root.

    Creates docs/specs/ if it does not already exist. Write-only: performs no
    git operation (the caller, /solomon-issue, stays git-free by design).

    Raises OSError on a failed write (for example, a read-only filesystem);
    the error is re-raised carrying only the file's basename, never the full
    (potentially absolute) path, so a caller that reports it cannot leak one.
    """
    docs_specs = root / "docs" / "specs"
    docs_specs.mkdir(parents=True, exist_ok=True)
    path = docs_specs / spec_filename(issue_number, title)
    try:
        path.write_text(render_spec(issue_number, title, body, adr_ref=adr_ref), encoding="utf-8")
    except OSError as exc:
        raise OSError(exc.errno, exc.strerror or str(exc), path.name) from exc
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a spec document per issue.")
    sub = parser.add_subparsers(dest="command")

    p_generate = sub.add_parser(
        "generate", help="Generate docs/specs/<N>-<slug>.md from an issue body"
    )
    p_generate.add_argument("--issue", type=int, required=True)
    p_generate.add_argument("--title", required=True)
    p_generate.add_argument("--body-file", required=True)
    p_generate.add_argument("--adr", default=None, help="ADR reference by number/title.")
    p_generate.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repository root (default: the repository containing this module).",
    )

    args = parser.parse_args(argv)

    if args.command != "generate":
        parser.print_help()
        return 1

    root = Path(args.root)
    try:
        body = Path(args.body_file).read_text(encoding="utf-8")
        path = write_spec(root, args.issue, args.title, body, adr_ref=args.adr)
    except OSError as exc:
        # One clean stderr line, never a raw traceback, and never an
        # absolute path: only the basename and the OS's own error text.
        name = Path(exc.filename).name if exc.filename else Path(args.body_file).name
        reason = exc.strerror or str(exc)
        print(f"error: {reason}: {name}", file=sys.stderr)
        return 1

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    # Write-only by design: /solomon-issue stays git-free (main is protected),
    # so this never commits or pushes the file it just wrote.
    print(f"Created {rel} (uncommitted).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
