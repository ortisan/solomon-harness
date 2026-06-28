"""Headless runner for the /solomon-dev-* delivery workflows.

`run_stage` builds the prompt from the matching `.claude/commands/solomon-dev-<stage>.md`
file and runs it through the chosen engine (claude or gemini) non-interactively,
so the workflows can run in CI and automation, not only inside the host tool.
"""

import os
import subprocess
import sys
from typing import List, Optional

STAGES = ["idea", "issue", "bug", "refine", "start", "review", "release"]


def build_prompt(workspace_root: str, stage: str, args: List[str]) -> str:
    """Return the command body for a stage with $ARGUMENTS substituted."""
    cmd_file = os.path.join(workspace_root, ".claude", "commands", f"solomon-dev-{stage}.md")
    if not os.path.isfile(cmd_file):
        raise FileNotFoundError(cmd_file)
    with open(cmd_file, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        # Drop the YAML frontmatter, keep the prompt body.
        text = "---".join(text.split("---")[2:]).strip()
    return text.replace("$ARGUMENTS", " ".join(args))


def run_stage(
    workspace_root: str,
    stage: str,
    args: List[str],
    engine: Optional[str] = None,
) -> int:
    """Run one workflow stage headless through the selected engine."""
    if stage not in STAGES:
        print(f"Error: unknown stage '{stage}'. Stages: {', '.join(STAGES)}", file=sys.stderr)
        return 1
    engine = (engine or os.environ.get("SOLOMON_ENGINE") or "claude").lower()
    if engine not in ("claude", "gemini"):
        print(f"Error: unknown engine '{engine}'. Use 'claude' or 'gemini'.", file=sys.stderr)
        return 1
    try:
        prompt = build_prompt(workspace_root, stage, args)
    except FileNotFoundError as exc:
        print(f"Error: command file not found ({exc}). Run 'solomon-harness init' first.", file=sys.stderr)
        return 1

    print(f"Running /solomon-dev-{stage} headless via {engine}...")
    try:
        proc = subprocess.run([engine, "-p"], input=prompt, text=True, check=False)
    except FileNotFoundError:
        print(f"Error: '{engine}' is not installed or not authenticated.", file=sys.stderr)
        return 1
    return proc.returncode
