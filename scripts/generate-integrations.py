#!/usr/bin/env python3
"""Generate host-tool integrations from the canonical Solomon sources.

This emits one Claude Code subagent per specialist agent, mirrors the canonical
Claude workflow commands into Gemini commands, and renders the same workflows
as Codex skills. Run from the repository root:

    python scripts/generate-integrations.py
"""

import os
import re
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from solomon_harness.integrations import (  # noqa: E402
    discover_agents as discover_agents,
    generate_claude_agents,
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
    """Mirror the .claude/commands/*.md commands into .gemini/commands/*.toml."""
    src_dir = os.path.join(workspace_root, ".claude", "commands")
    if not os.path.isdir(src_dir):
        return 0
    out_dir = os.path.join(workspace_root, ".gemini", "commands")
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".md"):
            continue
        description, body = _parse_command_file(os.path.join(src_dir, name))
        toml = gemini_command_toml(description, body)
        with open(os.path.join(out_dir, name[:-3] + ".toml"), "w", encoding="utf-8") as f:
            f.write(toml)
        count += 1
    if count:
        print(f"Generated {count} Gemini commands in {out_dir}")
    return count


def codex_skill_markdown(skill_name: str, description: str, body: str) -> str:
    """Render a canonical workflow command as a Codex skill.

    Codex skills receive their arguments through the conversation rather than a
    custom-prompt substitution pass. ``ARGUMENTS`` is therefore a documented
    symbolic name inside the generated workflow, not an unresolved placeholder.
    """
    trigger = (
        f"{description.rstrip()} Use when the user asks to run the corresponding "
        f"Solomon stage or explicitly invokes ${skill_name}."
    )
    portable_body = re.sub(
        r"(?<![A-Za-z0-9_./-])/solomon-",
        "$solomon-",
        body.replace("$ARGUMENTS", "ARGUMENTS"),
    )
    return (
        "---\n"
        f"name: {skill_name}\n"
        f"description: {yaml_quote(trigger)}\n"
        "---\n\n"
        f"# {skill_name}\n\n"
        "Apply this workflow when the user invokes the skill or asks for the "
        "stage it governs. Treat `ARGUMENTS` in the workflow below as the "
        "arguments supplied with the skill invocation or elsewhere in the "
        "conversation.\n\n"
        "Codex compatibility rules:\n\n"
        "- Invoke Solomon workflow stages explicitly with their `$solomon-*` "
        "skill names.\n"
        "- When the workflow names Claude-specific Task or AskUserQuestion tools, "
        "use the equivalent sub-agent delegation or structured user-input "
        "capability available in the current Codex session.\n"
        "- Read specialist definitions and skills under `agents/<name>/` before "
        "acting in that role.\n\n"
        f"{portable_body}\n"
    )


def generate_codex_skills(workspace_root: str) -> int:
    """Render every canonical Solomon command into ``.agents/skills``."""
    src_dir = os.path.join(workspace_root, ".claude", "commands")
    if not os.path.isdir(src_dir):
        return 0
    out_dir = os.path.join(workspace_root, ".agents", "skills")
    os.makedirs(out_dir, exist_ok=True)
    active = set()
    for name in sorted(os.listdir(src_dir)):
        if not name.startswith("solomon-") or not name.endswith(".md"):
            continue
        skill_name = name[:-3]
        active.add(skill_name)
        description, body = _parse_command_file(os.path.join(src_dir, name))
        skill_dir = os.path.join(out_dir, skill_name)
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(codex_skill_markdown(skill_name, description, body))

    for name in os.listdir(out_dir):
        path = os.path.join(out_dir, name)
        if name.startswith("solomon-") and name not in active and os.path.isdir(path):
            shutil.rmtree(path)

    if active:
        print(f"Generated {len(active)} Codex skills in {out_dir}")
    return len(active)


def generate(workspace_root: str) -> int:
    agents_dir = os.path.join(workspace_root, "agents")
    if not os.path.isdir(agents_dir):
        print(f"Error: agents directory not found at {agents_dir}", file=sys.stderr)
        return 1

    generate_claude_agents(workspace_root, harness_style=True)

    # Mirror the workflows into Gemini commands and Codex skills.
    generate_gemini_commands(workspace_root)
    generate_codex_skills(workspace_root)
    return 0


if __name__ == "__main__":
    sys.exit(generate(WORKSPACE_ROOT))
