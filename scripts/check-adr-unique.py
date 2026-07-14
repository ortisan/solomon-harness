#!/usr/bin/env python3
"""Validate that every ADR has a unique number that matches its H1 title.

Scans the ADR directory (``docs/adrs`` by default), skipping the template and the
README index. For each ADR file it reads the leading number from the filename
and the number in the H1 line (``# ADR-NNNN: ...``). It exits non-zero if any
number is shared by more than one file, or if a file's filename number and H1
number disagree. On success it prints ``OK`` and exits zero.

Run it from the repository root or point it at a directory:

    python scripts/check-adr-unique.py
    python scripts/check-adr-unique.py path/to/adr
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXCLUDED = {"README.md", "0000-adr-template.md"}
FILENAME_RE = re.compile(r"^(\d{4})-")
H1_RE = re.compile(r"^#\s*ADR-(\d{4}):")


def _h1_number(path: Path) -> str | None:
    """Return the four-digit number from the first H1 line, or None if absent."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            match = H1_RE.match(stripped)
            return match.group(1) if match else None
    return None


def check(adr_dir: Path) -> list[str]:
    """Return a list of problems found in adr_dir; an empty list means valid."""
    errors: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(adr_dir.glob("*.md")):
        if path.name in EXCLUDED:
            continue
        name_match = FILENAME_RE.match(path.name)
        if not name_match:
            errors.append(
                f"{path.name}: filename does not start with a four-digit ADR number"
            )
            continue
        number = name_match.group(1)
        h1 = _h1_number(path)
        if h1 is None:
            errors.append(f"{path.name}: missing or malformed 'ADR-NNNN:' H1 heading")
        elif h1 != number:
            errors.append(
                f"{path.name}: filename number {number} does not match H1 number {h1}"
            )
        if number in seen:
            errors.append(
                f"duplicate ADR number {number}: {seen[number]} and {path.name}"
            )
        else:
            seen[number] = path.name
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check ADR numbers are unique and match their H1 titles."
    )
    default_dir = Path(__file__).resolve().parent.parent / "docs" / "adrs"
    parser.add_argument(
        "adr_dir",
        nargs="?",
        default=str(default_dir),
        help="Directory containing ADR markdown files (default: docs/adrs).",
    )
    args = parser.parse_args(argv)

    adr_dir = Path(args.adr_dir)
    if not adr_dir.is_dir():
        print(f"ADR directory not found: {adr_dir}", file=sys.stderr)
        return 2

    errors = check(adr_dir)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
