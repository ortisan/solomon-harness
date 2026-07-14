#!/usr/bin/env python3
"""Machine-checkable ADR gate over a pull-request body (#221 S2b, #235).

Every PR body must carry exactly one canonical ADR line:

    ADR: docs/adrs/NNNN-<slug>.md        (the decision record this change made)
    ADR: not warranted — <reason>        (the explicit decision to skip)

Old-path links (docs/adr/...) fail post-migration; carrying both forms fails
as ambiguous; a skip without a reason fails. The gate owns the body contract
only — the linked file's existence and numbering stay with check-adr-unique
and the review gate.

Usage:
    python scripts/check-adr-gate.py --body-file <path>
    PR_BODY="..." python scripts/check-adr-gate.py --env PR_BODY

Exit codes: 0 contract met, 1 contract violated, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# The canonical output form uses the em dash, but the validator tolerates the
# dashes humans and hosts actually type (em, en, --, -): the contract is the
# decision statement, not the typography.
DASH = r"(?:—|–|--|-)"
ADR_LINK = re.compile(r"^ADR: docs/adrs/\d{4}-[a-z0-9-]+\.md\s*$", re.MULTILINE)
ADR_SKIP = re.compile(rf"^ADR: not warranted {DASH} (?P<reason>.+)$", re.MULTILINE)
ADR_SKIP_BARE = re.compile(rf"^ADR: not warranted(?: {DASH})?\s*$", re.MULTILINE)
OLD_PATH_LINK = re.compile(r"^ADR: docs/adr/", re.MULTILINE)
ANY_ADR_LINE = re.compile(r"^ADR: ", re.MULTILINE)
INDENTED_ADR_LINE = re.compile(r"^[ \t]+ADR: ", re.MULTILINE)
FENCED_BLOCK = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)


def check_body(body: str) -> list[str]:
    """Return the list of contract violations (empty == the gate passes)."""
    # A canonical line inside a fenced code block is illustration, not a
    # decision: strip fences before matching.
    prose = FENCED_BLOCK.sub("", body)
    links = ADR_LINK.findall(prose)
    skips = ADR_SKIP.findall(prose)
    problems: list[str] = []
    if OLD_PATH_LINK.search(prose):
        problems.append(
            "the ADR line links the pre-migration docs/adr/ path — records "
            "live under docs/adrs/ (ADR-0028)"
        )
    if ADR_SKIP_BARE.search(prose):
        problems.append(
            "the skip line must carry a reason: 'ADR: not warranted — <reason>'"
        )
    if len(links) + len(skips) > 1:
        problems.append(
            "the body carries more than one ADR line — one decision, one line"
        )
    if not links and not skips and not problems:
        if ANY_ADR_LINE.search(prose):
            problems.append(
                "an 'ADR:' line is present but matches neither canonical form "
                "('ADR: docs/adrs/NNNN-<slug>.md' or 'ADR: not warranted — <reason>')"
            )
        elif INDENTED_ADR_LINE.search(prose):
            problems.append(
                "an indented ADR line is not recognized — start the canonical "
                "line at column 1"
            )
        else:
            problems.append(
                "the body carries no ADR line — add 'ADR: docs/adrs/NNNN-<slug>.md' "
                "or 'ADR: not warranted — <reason>'"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--body-file", help="File holding the PR body text")
    source.add_argument(
        "--env", help="Environment variable holding the PR body text"
    )
    args = parser.parse_args()

    if args.body_file:
        try:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError as exc:
            print(f"cannot read body file: {exc}", file=sys.stderr)
            return 2
    else:
        if args.env not in os.environ:
            print(f"environment variable '{args.env}' is not set", file=sys.stderr)
            return 2
        body = os.environ[args.env]

    problems = check_body(body)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("OK  the PR body meets the ADR contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
