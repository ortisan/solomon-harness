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
import sys
from typing import Dict, List, Optional

from solomon_harness.home import assigned_memory_port, harness_home
from solomon_harness.memory import _set_published_port

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


def _register_mcp(add_args: List[str], cli: str, server: str = "solomon-memory") -> Optional[bool]:
    """Best-effort: register the MCP server with a host CLI, idempotently.

    Removes any existing registration first (``mcp add`` refuses to overwrite),
    then adds. Returns True on success, False on failure, None if the CLI is
    absent. Never raises; the user can register manually if this does not apply.
    """
    if not shutil.which(cli):
        return None
    try:
        subprocess.run(
            [cli, "mcp", "remove", "--scope", "user", server],
            capture_output=True, text=True, check=False,
        )
        proc = subprocess.run(
            [cli, *add_args],
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
        with open(src_compose, "r", encoding="utf-8") as f:
            content = f.read()
        # Template the auto-assigned host port so the shared backend does not
        # re-introduce the 8000 collision this whole design exists to avoid.
        port = assigned_memory_port(home_dir)
        content = _set_published_port(content, port)
        with open(os.path.join(home_dir, "docker-compose.yml"), "w", encoding="utf-8") as f:
            f.write(content)
        result["home_compose"] = True
        result["memory_port"] = port

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

    # 3. Global Gemini commands (legacy format).
    result["gemini_commands"] = _copy_dir_contents(
        os.path.join(source_root, ".gemini", "commands"),
        os.path.join(gemini_dir, "commands"),
        (".toml",),
    )

    # 3.5. New Antigravity/Gemini CLI extension format.
    ext_dir = os.path.join(gemini_dir, "extensions", "solomon")
    os.makedirs(os.path.join(ext_dir, "commands"), exist_ok=True)
    _copy_dir_contents(
        os.path.join(source_root, ".gemini", "commands"),
        os.path.join(ext_dir, "commands"),
        (".toml",),
    )
    # Write gemini-extension.json
    ext_manifest = {
        "name": "solomon",
        "version": "1.0.0",
        "description": "Solomon Harness Commands"
    }
    with open(os.path.join(ext_dir, "gemini-extension.json"), "w", encoding="utf-8") as f:
        json.dump(ext_manifest, f, indent=4)
    result["gemini_extension"] = True

    # If agy CLI is present and we are installing to the default ~/.gemini,
    # automatically run import to convert to Antigravity plugin/skills
    is_default_gemini = os.path.abspath(gemini_dir) == os.path.abspath(os.path.expanduser("~/.gemini"))
    if is_default_gemini:
        agy_bin = shutil.which("agy")
        if not agy_bin:
            candidate = os.path.expanduser("~/.local/bin/agy")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                agy_bin = candidate
            elif os.name == "nt":
                win_candidate = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
                if os.path.isfile(win_candidate):
                    agy_bin = win_candidate

        if agy_bin:
            try:
                subprocess.run(
                    [agy_bin, "plugin", "import", "gemini", "--force"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                result["agy_imported"] = True
            except Exception:
                result["agy_imported"] = False
        else:
            result["agy_imported"] = None
    else:
        result["agy_imported"] = None

    # 4. SessionStart hook in the global Claude settings.
    result["hook_installed"] = _merge_session_start_hook(
        os.path.join(claude_dir, "settings.json")
    )

    # 5. Best-effort MCP registration with the host CLIs (user scope).
    if register_mcp:
        # Use the current interpreter (the venv that has solomon_harness
        # installed); a bare "python3" usually cannot import the package.
        result["mcp_claude"] = _register_mcp(
            ["mcp", "add", "--scope", "user", "solomon-memory", "--",
             sys.executable, "-m", "solomon_harness.mcp_server"],
            "claude",
        )

    return result


def describe(result: dict) -> str:
    """Human summary of an install_global result."""
    lines = ["Global install:"]
    port = result.get("memory_port")
    port_note = f" (SurrealDB host port {port})" if port else ""
    lines.append(f"  shared home: agents={result.get('home_agents', False)} compose={result.get('home_compose', False)}{port_note}")
    lines.append(f"  ~/.claude: {len(result.get('claude_agents', []))} agents, {len(result.get('claude_commands', []))} commands")
    lines.append(f"  ~/.gemini: {len(result.get('gemini_commands', []))} legacy commands, extension={result.get('gemini_extension', False)}")
    agy_imported = result.get("agy_imported")
    if agy_imported is True:
        lines.append("  ~/.gemini (Antigravity): successfully imported and converted extension to plugins/skills")
    elif agy_imported is False:
        lines.append("  ~/.gemini (Antigravity): import run failed")
    elif agy_imported is None and result.get("gemini_extension"):
        # Only show note if extension was processed but agy wasn't found/run
        lines.append("  ~/.gemini (Antigravity): agy CLI not found or non-default path; no import executed")
    lines.append(f"  session hook: {'installed' if result.get('hook_installed') else 'already present'}")
    mcp = result.get("mcp_claude")
    if mcp is None:
        lines.append("  MCP: claude CLI not found; register manually with 'claude mcp add --scope user solomon-memory -- python3 -m solomon_harness.mcp_server'")
    else:
        lines.append(f"  MCP (claude, user scope): {'registered' if mcp else 'registration failed; do it manually'}")
    return "\n".join(lines)
