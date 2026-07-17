"""Packaged fallback for compiling project-local Claude specialist agents.

Projects may keep their own ``scripts/generate-integrations.py`` when they need
the full multi-host generator. This module supplies the safe minimum when that
script is absent, so an installed harness can still compile ``agents/`` into
Claude Code subagents without copying executable harness code into the project.
"""

import os
import re
import stat
import tempfile
from typing import List

MAX_ROLE_BYTES = 64 * 1024
MAX_ROLE_LINE_CHARS = 2048
AGENT_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


def _is_confined_without_symlinks(path: str, root: str) -> bool:
    """Return whether path stays under root without crossing a symlink."""
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    try:
        if os.path.commonpath((root, path)) != root:
            return False
    except ValueError:
        return False

    current = root
    if os.path.islink(current):
        return False
    relative = os.path.relpath(path, root)
    for part in relative.split(os.sep):
        if part == ".":
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            return False
    return True


def _safe_regular_file(path: str, root: str, max_bytes: int = 0) -> bool:
    if not _is_confined_without_symlinks(path, root):
        return False
    try:
        file_stat = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    if not stat.S_ISREG(file_stat.st_mode):
        return False
    return not max_bytes or file_stat.st_size <= max_bytes


def _safe_directory(path: str, root: str) -> bool:
    if not _is_confined_without_symlinks(path, root):
        return False
    try:
        return stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode)
    except OSError:
        return False


def discover_agents(agents_dir: str) -> List[str]:
    """Return canonical, confined agent directories safe to compile."""
    if not _safe_directory(agents_dir, agents_dir):
        return []
    names = []
    for item in sorted(os.listdir(agents_dir)):
        if not AGENT_NAME_PATTERN.fullmatch(item):
            continue
        agent_dir = os.path.join(agents_dir, item)
        role = os.path.join(agent_dir, "agents", f"{item}.md")
        persona = os.path.join(agent_dir, "persona.md")
        skills = os.path.join(agent_dir, "skills")
        if (
            _safe_regular_file(role, agents_dir, MAX_ROLE_BYTES)
            and _safe_regular_file(persona, agents_dir)
            and _safe_directory(skills, agents_dir)
        ):
            names.append(item)
    return names


def role_description(role_path: str, agent_name: str, agents_dir: str) -> str:
    """Build the host description from the role one-liner and delegation cue."""
    fallback = f"The {agent_name} specialist for this project."
    if not _safe_regular_file(role_path, agents_dir, MAX_ROLE_BYTES):
        return fallback
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(role_path, flags)
        with os.fdopen(descriptor, "rb") as f:
            file_stat = os.fstat(f.fileno())
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_ROLE_BYTES:
                return fallback
            content = f.read(MAX_ROLE_BYTES + 1)
        if len(content) > MAX_ROLE_BYTES:
            return fallback
        lines = content.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return fallback
    if any(len(line) > MAX_ROLE_LINE_CHARS for line in lines):
        return fallback

    one_liner = ""
    cue = ""
    in_cue = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_cue = stripped.lower() == "## delegation cue"
            continue
        if not stripped or stripped.startswith("#"):
            continue
        if in_cue:
            cue = stripped
            break
        if not one_liner:
            one_liner = stripped
    if one_liner and cue:
        return f"{one_liner} {cue}"
    return one_liner or fallback


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _trust_root(workspace_root: str) -> str:
    """Return the existing project instruction file a subagent must read."""
    candidates = (
        (os.path.join("agents", "AGENTS.md"), "agents/AGENTS.md"),
        ("AGENTS.md", "AGENTS.md"),
    )
    for filesystem_path, markdown_path in candidates:
        if _safe_regular_file(
            os.path.join(workspace_root, filesystem_path), workspace_root
        ):
            return markdown_path
    raise FileNotFoundError(
        "cannot compile agents without agents/AGENTS.md or AGENTS.md project instructions"
    )


def _integration_output_dir(workspace_root: str) -> str:
    """Create and validate the output path without following directory symlinks."""
    if not _safe_directory(workspace_root, workspace_root):
        raise ValueError(f"unsafe integration output directory: {workspace_root}")
    current = workspace_root
    for component in (".claude", "agents"):
        current = os.path.join(current, component)
        if os.path.lexists(current):
            if not _safe_directory(current, workspace_root):
                raise ValueError(f"unsafe integration output directory: {current}")
            continue
        os.mkdir(current)
        if not _safe_directory(current, workspace_root):
            raise ValueError(f"unsafe integration output directory: {current}")
    return current


def _atomic_write(path: str, content: str, output_dir: str, workspace_root: str) -> None:
    """Replace one generated file atomically without following its prior target."""
    if not _safe_directory(output_dir, workspace_root):
        raise ValueError(f"unsafe integration output directory: {output_dir}")
    descriptor, temp_path = tempfile.mkstemp(
        dir=output_dir,
        prefix=".solomon-integration-",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            f.write(content)
        if not _safe_directory(output_dir, workspace_root):
            raise ValueError(f"unsafe integration output directory: {output_dir}")
        os.replace(temp_path, path)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def subagent_markdown(agent_name: str, description: str, trust_root: str) -> str:
    """Render a thin Claude Code subagent bound to existing project sources."""
    return (
        "---\n"
        f"name: {agent_name}\n"
        f"description: {_yaml_quote(description)}\n"
        "model: sonnet\n"
        "---\n\n"
        f"You are the {agent_name} specialist agent for this project.\n\n"
        f"Your role is defined in `agents/{agent_name}/agents/{agent_name}.md` and your "
        f"persona in `agents/{agent_name}/persona.md`. Your skills are in "
        f"`agents/{agent_name}/skills/`. The shared project rules are in `{trust_root}`. "
        "Read those files first, then act strictly within them.\n\n"
        f"Always follow `{trust_root}`. When relevant, persist decisions and handoffs "
        "through the project's configured memory integration.\n\n"
        "This file is generated by `solomon-harness compile`. Edit the source under "
        f"`agents/{agent_name}/`, not this file.\n"
    )


def generate_claude_agents(workspace_root: str) -> int:
    """Compile canonical project agents into ``.claude/agents``."""
    agents_dir = os.path.join(workspace_root, "agents")
    names = discover_agents(agents_dir)
    if not names:
        return 0

    trust_root = _trust_root(workspace_root)
    out_dir = _integration_output_dir(workspace_root)
    for name in names:
        role = os.path.join(agents_dir, name, "agents", f"{name}.md")
        description = role_description(role, name, agents_dir)
        destination = os.path.join(out_dir, f"{name}.md")
        content = subagent_markdown(name, description, trust_root)
        _atomic_write(destination, content, out_dir, workspace_root)

    print(f"Generated {len(names)} Claude Code subagents in {out_dir}: {', '.join(names)}")
    return len(names)
