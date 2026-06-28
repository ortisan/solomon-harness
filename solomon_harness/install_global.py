"""Install the harness once into the user-global locations so projects share it.

The chosen model keeps zero per-project duplication: the agent subagents and the
``/solomon-*`` commands live in the user-global ``~/.claude`` (and ``~/.gemini``)
so every project sees them, and the single memory backend lives in the shared
``~/.solomon-harness`` home. A project then carries only its ``.agent/config.json``
(its tenant). This module performs that global install; it merges rather than
clobbers, and is idempotent.
"""

import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional

from solomon_harness.home import harness_home

MEMORY_UP_CMD = "uv run python -m solomon_harness.cli memory-up 2>/dev/null || true"
RUN_CMD = "uv run python -m solomon_harness.cli run 2>/dev/null || true"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _copy_dir_contents(src: str, dest: str, suffixes: tuple) -> List[str]:
    """Copy files with the given suffixes from src into dest. Returns names copied."""
    copied = []
    if not os.path.isdir(src):
        return copied
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if not name.endswith(suffixes):
            continue
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copyfile(s, os.path.join(dest, name))
            copied.append(name)
    return copied


def _merge_session_start_hook(settings_path: str) -> bool:
    """Add the memory-up + run SessionStart hooks to a Claude settings file.

    Idempotent: returns True if the file was changed. Existing unrelated hooks
    and settings are preserved.
    """
    settings: Dict = {}
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f) or {}
        except Exception:
            settings = {}

    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])

    # Already installed? Look for our memory-up command anywhere in SessionStart.
    existing = json.dumps(session_start)
    if "solomon_harness.cli memory-up" in existing:
        return False

    session_start.append({
        "hooks": [
            {"type": "command", "command": MEMORY_UP_CMD},
            {"type": "command", "command": RUN_CMD},
        ]
    })
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return True


def _register_mcp(scope_args: List[str], cli: str) -> Optional[bool]:
    """Best-effort: register the solomon-memory MCP server with a host CLI.

    Returns True on success, False on failure, None if the CLI is absent. Never
    raises; the user can register manually if this does not apply.
    """
    if not shutil.which(cli):
        return None
    try:
        proc = subprocess.run(
            [cli, *scope_args],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def install_global(
    *,
    source_root: Optional[str] = None,
    claude_dir: Optional[str] = None,
    gemini_dir: Optional[str] = None,
    home_dir: Optional[str] = None,
    register_mcp: bool = True,
) -> dict:
    """Install agents, commands, the session hook, and the shared home globally.

    All target directories are parameters so the install can be exercised against
    temporary locations in tests. Returns a result dict summarizing what changed.
    """
    source_root = source_root or _repo_root()
    claude_dir = claude_dir or os.path.expanduser("~/.claude")
    gemini_dir = gemini_dir or os.path.expanduser("~/.gemini")
    home_dir = home_dir or harness_home()

    result: Dict = {"ok": True}

    # 1. Shared home: the canonical agent source + the single compose file.
    os.makedirs(home_dir, exist_ok=True)
    src_agents = os.path.join(source_root, "agents")
    if os.path.isdir(src_agents):
        dest_agents = os.path.join(home_dir, "agents")
        if os.path.isdir(dest_agents):
            shutil.rmtree(dest_agents)
        shutil.copytree(
            src_agents,
            dest_agents,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        result["home_agents"] = True
    src_compose = os.path.join(source_root, "docker-compose.yml")
    if os.path.isfile(src_compose):
        shutil.copyfile(src_compose, os.path.join(home_dir, "docker-compose.yml"))
        result["home_compose"] = True

    # 2. Global Claude subagents + commands (already generated in the package).
    result["claude_agents"] = _copy_dir_contents(
        os.path.join(source_root, ".claude", "agents"),
        os.path.join(claude_dir, "agents"),
        (".md",),
    )
    result["claude_commands"] = _copy_dir_contents(
        os.path.join(source_root, ".claude", "commands"),
        os.path.join(claude_dir, "commands"),
        (".md",),
    )

    # 3. Global Gemini commands.
    result["gemini_commands"] = _copy_dir_contents(
        os.path.join(source_root, ".gemini", "commands"),
        os.path.join(gemini_dir, "commands"),
        (".toml",),
    )

    # 4. SessionStart hook in the global Claude settings.
    result["hook_installed"] = _merge_session_start_hook(
        os.path.join(claude_dir, "settings.json")
    )

    # 5. Best-effort MCP registration with the host CLIs (user scope).
    if register_mcp:
        result["mcp_claude"] = _register_mcp(
            ["mcp", "add", "--scope", "user", "solomon-memory", "--",
             "python3", "-m", "solomon_harness.mcp_server"],
            "claude",
        )

    return result


def describe(result: dict) -> str:
    """Human summary of an install_global result."""
    lines = ["Global install:"]
    lines.append(f"  shared home: agents={result.get('home_agents', False)} compose={result.get('home_compose', False)}")
    lines.append(f"  ~/.claude: {len(result.get('claude_agents', []))} agents, {len(result.get('claude_commands', []))} commands")
    lines.append(f"  ~/.gemini: {len(result.get('gemini_commands', []))} commands")
    lines.append(f"  session hook: {'installed' if result.get('hook_installed') else 'already present'}")
    mcp = result.get("mcp_claude")
    if mcp is None:
        lines.append("  MCP: claude CLI not found; register manually with 'claude mcp add --scope user solomon-memory -- python3 -m solomon_harness.mcp_server'")
    else:
        lines.append(f"  MCP (claude, user scope): {'registered' if mcp else 'registration failed; do it manually'}")
    return "\n".join(lines)
