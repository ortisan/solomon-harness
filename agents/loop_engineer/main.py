#!/usr/bin/env python3
"""Thin agent entrypoint.

All harness logic lives in the importable solomon_harness package. This script
locates the package on disk, puts the repository root on sys.path, then hands
control to the shared CLI with this directory as the harness directory so the
loop uses this agent's config, persona and memory store.
"""

import os
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_repo_root(start: str) -> str:
    """Walks up from start to the directory that contains the solomon_harness package."""
    current = start
    while current and current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, "solomon_harness")):
            return current
        current = os.path.dirname(current)
    return start


def main() -> None:
    repo_root = _find_repo_root(HARNESS_DIR)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from solomon_harness.cli import main as cli_main

    cli_main(harness_dir=HARNESS_DIR)


if __name__ == "__main__":
    main()
