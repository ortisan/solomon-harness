#!/usr/bin/env python3
"""Compatibility entrypoint for the neutral three-host adapter compiler.

The compiler reads through ``HarnessPaths``: installed projects use the catalog
below ``.agents/solomon`` and this source repository may use the legacy source
locations for one migration window. It never generates legacy ``.gemini``
artifacts. Run from the repository root:

    uv run python -I scripts/generate-integrations.py
"""

import os
import sys
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from solomon_harness.integrations import (  # noqa: E402
    discover_agents as discover_agents,
    harness_subagent_markdown,
    role_description_from_text,
)


def role_description(role_path: str, agent_name: str) -> str:
    """Builds the subagent description from the role file: its opening line
    (what the agent does) plus the first line of the `## Delegation cue`
    section (when to delegate to it), so generated subagents carry a trigger
    condition, not just a role label."""
    try:
        with open(role_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    return role_description_from_text(
        text,
        agent_name,
        fallback=f"The {agent_name} specialist for solomon-harness.",
    )


def yaml_quote(value: str) -> str:
    """Render a single-line string as a double-quoted YAML scalar.

    Descriptions are natural-language sentences, so unquoted colons or hashes
    would break the generated frontmatter for any strict YAML consumer.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def subagent_markdown(agent_name: str, description: str) -> str:
    return harness_subagent_markdown(
        agent_name,
        description,
        "agents/AGENTS.md",
    )


def _parse_command_file(path: str):
    """Return (description, body) for a Claude Code command markdown file."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    description = ""
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            front, body = parts[1], parts[2]
            for line in front.splitlines():
                if line.strip().lower().startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                    break
    return description, body.strip()


def gemini_command_toml(description: str, body: str) -> str:
    """Render a Gemini CLI custom command (TOML) from a Claude command body.

    Claude's $ARGUMENTS becomes Gemini's {{args}}, and the Claude-specific
    mcp__solomon-memory__ tool prefix is dropped so the prompt is portable.
    """
    prompt = body.replace("$ARGUMENTS", "{{args}}").replace("mcp__solomon-memory__", "")
    desc = description.replace("\\", "\\\\").replace('"', '\\"')
    # Use a TOML multi-line literal string so the prompt needs no escaping.
    return f'description = "{desc}"\n\nprompt = \'\'\'\n{prompt}\n\'\'\'\n'


def generate_gemini_commands(workspace_root: str) -> int:
    """Deprecated compatibility shim; current AGY discovers ``.agents``."""
    del workspace_root
    return 0


def generate(workspace_root: str, *, installed: bool | None = None) -> int:
    """Delegate generation to the canonical Claude, AGY, and Codex compiler."""
    from solomon_harness.layout import HarnessPaths

    try:
        paths = HarnessPaths(workspace_root)
        installed = paths.manifest.is_file() if installed is None else installed
        if installed:
            from solomon_harness.install_layout import (
                compile_project_adapters,
                load_manifest,
            )

            install_result = compile_project_adapters(workspace_root)
            manifest = load_manifest(workspace_root)
            managed_count = sum(
                entry.get("owner") == "adapter"
                for entry in manifest.get("entries", [])
            )
            conflicts = install_result.conflicts
        else:
            from solomon_harness.host_adapters import compile_adapters

            adapter_result = compile_adapters(workspace_root)
            managed_count = len(adapter_result.managed_paths)
            conflicts = adapter_result.conflicts
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Error: adapter compilation failed ({exc})", file=sys.stderr)
        return 1
    if conflicts:
        print(
            "Error: adapter conflicts were preserved: " + ", ".join(conflicts),
            file=sys.stderr,
        )
        return 1
    print(f"Compiled {managed_count} Claude, AGY, and Codex adapter paths.")
    return 0


def _installed_entrypoint(script_file: str) -> bool:
    harness_root = Path(script_file).resolve().parent.parent
    return harness_root.name == "solomon" and harness_root.parent.name == ".agents"


def _workspace_root(script_file: str) -> str:
    """Resolve the consumer root when this entrypoint runs from an install."""

    harness_root = Path(script_file).resolve().parent.parent
    return os.fspath(
        harness_root.parent.parent
        if _installed_entrypoint(script_file)
        else harness_root
    )


if __name__ == "__main__":
    sys.exit(
        generate(
            _workspace_root(__file__),
            installed=_installed_entrypoint(__file__),
        )
    )
