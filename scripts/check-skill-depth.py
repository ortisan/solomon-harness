#!/usr/bin/env python3
"""Mechanical depth and format gate for agent skills (#6, #160).

The canonical depth bar from issue #6: every role-core skill file must be at least
600 words and close with `## Common pitfalls` and `## Definition of done`. Shared
checklist files are exempt from the word count because they are intentionally
short.

The format gate from issue #160: every agents/*/skills/*.md, with no exemptions,
must contain both mandated sections, use a snake_case filename, and open with
discovery frontmatter — a `name` matching the filename (underscores become
hyphens, per the Agent Skills naming charset) and a third-person `description`
of at most 1024 characters that states what the skill does and carries a
"Use when" trigger (agents/AGENTS.md, "Skill file format"). This scan always
runs over the whole repository, regardless of which agents are named for the
depth scan.

Usage:
  python scripts/check-skill-depth.py                 # whole roster
  python scripts/check-skill-depth.py software_architect sre
Exits 0 when every checked skill meets the bar, 1 otherwise (listing each gap).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_WORDS = 600
MAX_DESCRIPTION_CHARS = 1024
SHARED_EXEMPT = {
    "definition_of_done.md",
    "common_pitfalls.md",
    "scope_and_non_negotiables.md",
}
REQUIRED_SECTIONS = ("## Common pitfalls", "## Definition of done")
# An agent name maps to a directory under agents/; constrain it so a stray `..`
# or absolute-path argument cannot redirect the scan outside the repo.
VALID_AGENT = re.compile(r"^[a-z0-9_]+$")
# The mandated filename shape for a skill file (agents/AGENTS.md).
SNAKE_CASE = re.compile(r"^[a-z0-9_]+\.md$")

REPO_ROOT = Path(__file__).resolve().parent.parent


def default_agents() -> list[str]:
    """Every agent with a skills directory: the depth bar covers the whole
    roster unless specific agents are named on the command line."""
    agents_root = REPO_ROOT / "agents"
    if not agents_root.is_dir():
        return []
    return sorted(path.parent.name for path in agents_root.glob("*/skills") if path.is_dir())


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading frontmatter block into (fields, body).

    Minimal single-line `key: value` parsing is all the skill contract needs;
    a missing or unterminated block returns ({}, text) unchanged.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields, text[end + 5 :]


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def check_skill(path: Path) -> list[str]:
    """Return a list of gap descriptions for one skill file (empty == passes).

    Depth is measured on the body only: frontmatter is discovery metadata and
    must not pad a shallow skill over the bar.
    """
    text = path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    gaps: list[str] = []
    words = word_count(body)
    if words < MIN_WORDS:
        gaps.append(f"{words}w < {MIN_WORDS}w")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            gaps.append(f"missing '{section}'")
    return gaps


def check_format(path: Path) -> list[str]:
    """Return the format gaps for one skill file (empty == passes).

    The mandated shape, with no exemptions: a snake_case filename, discovery
    frontmatter (name matching the filename stem with hyphens, a non-empty
    "Use when" description of at most 1024 characters), and both
    `## Common pitfalls` and `## Definition of done` sections.
    """
    gaps: list[str] = []
    if not SNAKE_CASE.match(path.name):
        gaps.append("filename not snake_case")
    text = path.read_text(encoding="utf-8")
    fields, _ = parse_frontmatter(text)
    if not fields:
        gaps.append("missing frontmatter")
    else:
        expected_name = path.stem.replace("_", "-")
        name = fields.get("name", "")
        if name != expected_name:
            gaps.append(f"frontmatter name '{name}' != '{expected_name}'")
        description = fields.get("description", "")
        if not description:
            gaps.append("missing frontmatter description")
        elif len(description) > MAX_DESCRIPTION_CHARS:
            gaps.append(
                f"description {len(description)} chars > {MAX_DESCRIPTION_CHARS}"
            )
        elif "Use when" not in description:
            gaps.append("description lacks a 'Use when' trigger")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            gaps.append(f"missing '{section}'")
    return gaps


def scan_format(root: Path) -> list[str]:
    """Check every agents/*/skills/*.md under root against the format gate."""
    failures: list[str] = []
    for path in sorted(root.glob("agents/*/skills/*.md")):
        gaps = check_format(path)
        if gaps:
            failures.append(f"{path.relative_to(root)}: {'; '.join(gaps)}")
    return failures


def main(argv: list[str]) -> int:
    agents = argv or default_agents()
    failures = 0
    checked = 0
    for agent in agents:
        if not VALID_AGENT.match(agent):
            print(f"FAIL  {agent}: invalid agent name")
            failures += 1
            continue
        skills_dir = REPO_ROOT / "agents" / agent / "skills"
        if not skills_dir.is_dir():
            print(f"FAIL  {agent}: no skills dir at {skills_dir}")
            failures += 1
            continue
        for path in sorted(skills_dir.glob("*.md")):
            if path.name in SHARED_EXEMPT:
                continue
            checked += 1
            gaps = check_skill(path)
            if gaps:
                failures += 1
                rel = path.relative_to(REPO_ROOT)
                print(f"FAIL  {rel}: {'; '.join(gaps)}")
    format_failures = scan_format(REPO_ROOT)
    for line in format_failures:
        print(f"FAIL  {line}")
    failures += len(format_failures)
    if failures:
        print(f"\n{failures} skill(s) below the canonical depth or format bar ({checked} checked).")
        return 1
    print(
        f"OK  {checked} role-core skills meet the depth bar; all skill files meet the format gate."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
