"""Shared parser for skill discovery frontmatter (ADR-0026).

This is the single implementation behind scripts/check-skill-depth.py (the CI
format gate) and scripts/document-skills.py (the profile generator). Keeping
one parser guarantees the gate and the generator can never disagree about what
counts as frontmatter — a file that passes the gate is parsed identically when
its description is baked into a profile.

The dialect is deliberately minimal: a leading ``---`` fence line, one
``key: value`` pair per line, and a closing ``---`` fence. Fence and field
lines tolerate surrounding whitespace and CRLF line endings. A missing or
unterminated block is not frontmatter: the caller gets ``({}, text)`` back
unchanged.
"""

from __future__ import annotations


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split ``text`` into (frontmatter fields, body).

    Returns ``({}, text)`` when no complete frontmatter block is present.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            fields: dict[str, str] = {}
            for raw in lines[1:index]:
                if ":" in raw:
                    key, value = raw.split(":", 1)
                    fields[key.strip()] = value.strip()
            return fields, "".join(lines[index + 1 :])
    return {}, text
