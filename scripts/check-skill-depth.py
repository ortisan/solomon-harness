#!/usr/bin/env python3
"""Mechanical depth and format gate for agent skills (#6, #160).

The canonical depth bar from issue #6: every role-core skill file must be at least
600 words and close with `## Common pitfalls` and `## Definition of done`. Shared
checklist files are exempt from the word count because they are intentionally
short.

The format gate from issue #160: every agents/*/skills/*.md, with no exemptions,
must contain both mandated sections and use a snake_case filename
(agents/AGENTS.md, "Skill file format"). This scan always runs over the whole
repository, regardless of which agents are named for the depth scan.

Usage:
  python scripts/check-skill-depth.py                 # default agents
  python scripts/check-skill-depth.py software_architect sre
Exits 0 when every checked skill meets the bar, 1 otherwise (listing each gap).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_WORDS = 600
SHARED_EXEMPT = {
    "definition_of_done.md",
    "common_pitfalls.md",
    "scope_and_non_negotiables.md",
}
REQUIRED_SECTIONS = ("## Common pitfalls", "## Definition of done")
DEFAULT_AGENTS = ("software_architect", "sre")
# An agent name maps to a directory under agents/; constrain it so a stray `..`
# or absolute-path argument cannot redirect the scan outside the repo.
VALID_AGENT = re.compile(r"^[a-z0-9_]+$")
# The mandated filename shape for a skill file (agents/AGENTS.md).
SNAKE_CASE = re.compile(r"^[a-z0-9_]+\.md$")

REPO_ROOT = Path(__file__).resolve().parent.parent


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def check_skill(path: Path) -> list[str]:
    """Return a list of gap descriptions for one skill file (empty == passes)."""
    text = path.read_text(encoding="utf-8")
    gaps: list[str] = []
    words = word_count(text)
    if words < MIN_WORDS:
        gaps.append(f"{words}w < {MIN_WORDS}w")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            gaps.append(f"missing '{section}'")
    return gaps


def check_format(path: Path) -> list[str]:
    """Return the format gaps for one skill file (empty == passes).

    The mandated shape, with no exemptions: a snake_case filename and both
    `## Common pitfalls` and `## Definition of done` sections.
    """
    gaps: list[str] = []
    if not SNAKE_CASE.match(path.name):
        gaps.append("filename not snake_case")
    text = path.read_text(encoding="utf-8")
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
    agents = argv or list(DEFAULT_AGENTS)
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
