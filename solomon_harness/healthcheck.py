"""Healthcheck: report the harness's runtime readiness and pending init items.

Where ``doctor`` checks and installs prerequisites, this reports the live state
that matters at session start: is the Docker daemon running, is the shared
memory backend actually serving (or has it fallen back to SQLite, and why), is
the GitHub board enabled, is the global install in place. Each check returns a
status (ok | warn | fail) and, when not ok, a one-line fix. It never raises.
"""

import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional

from solomon_harness import memory
from solomon_harness.home import assigned_memory_port, derive_tenant, harness_home

OK, WARN, FAIL = "ok", "warn", "fail"


def _check(name: str, status: str, detail: str, fix: str = "") -> Dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def _run(cmd: List[str]) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=8)
    except Exception:
        return None


def check_docker() -> Dict:
    """Docker installed AND the daemon actually running (the common pending item)."""
    if not shutil.which("docker"):
        return _check(
            "Docker", WARN, "not installed",
            "Install Docker to run the shared SurrealDB; the harness uses SQLite without it.",
        )
    proc = _run(["docker", "info"])
    if proc is None or proc.returncode != 0:
        return _check(
            "Docker daemon", WARN, "installed but not running",
            "Start Docker, then run 'solomon-harness memory-up'.",
        )
    return _check("Docker daemon", OK, "running")


def _db_config(workspace_root: str) -> Dict:
    path = os.path.join(workspace_root, ".agent", "config.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return (json.load(f) or {}).get("database", {}) or {}
        except Exception:
            return {}
    return {}


def check_memory(workspace_root: str) -> Dict:
    """Is the configured memory backend serving, or has it degraded (and why)?"""
    db = _db_config(workspace_root)
    provider = db.get("provider", "surrealdb")
    if provider != "surrealdb":
        return _check("Memory backend", OK, f"provider '{provider}' (no shared server needed)")
    host, port = memory._host_port(db.get("url", memory.DEFAULT_URL))
    configured = db.get("database")
    tenant = configured if configured not in (None, "", "harness") else derive_tenant(workspace_root)
    if memory.is_serving(host, port):
        return _check("Memory backend", OK, f"SurrealDB serving on {host}:{port} (tenant: {tenant})")
    if memory._tcp_open(host, port):
        return _check(
            "Memory backend", WARN,
            f"port {port} is held by a non-SurrealDB process; using SQLite fallback",
            f"Free port {port} (or change the configured URL), then 'solomon-harness memory-up'.",
        )
    return _check(
        "Memory backend", WARN,
        f"SurrealDB not running on {host}:{port}; using SQLite fallback (tenant: {tenant})",
        "Start Docker, then run 'solomon-harness memory-up'.",
    )


def check_github() -> Dict:
    """gh installed, authenticated, and carrying the project scope the board needs."""
    if not shutil.which("gh"):
        return _check(
            "GitHub CLI", WARN, "not installed",
            "Install gh to enable the project board and issue workflows.",
        )
    proc = _run(["gh", "auth", "status"])
    if proc is None or proc.returncode != 0:
        return _check("GitHub auth", WARN, "not authenticated", "Run 'gh auth login'.")
    text = (proc.stdout or "") + (proc.stderr or "")
    if "project" not in text:
        return _check(
            "GitHub board scope", WARN,
            "token is missing the 'project'/'read:project' scope; the board is disabled",
            "Run 'gh auth refresh -s project,read:project'.",
        )
    return _check("GitHub auth", OK, "authenticated with the project scope")


def check_global_install(claude_dir: Optional[str] = None) -> Dict:
    """Are the agents and /solomon commands installed in the user-global ~/.claude?"""
    claude_dir = claude_dir or os.path.expanduser("~/.claude")
    agents = os.path.join(claude_dir, "agents")
    commands = os.path.join(claude_dir, "commands")
    has_agents = os.path.isdir(agents) and any(n.endswith(".md") for n in os.listdir(agents))
    has_cmds = os.path.isdir(commands) and any(
        n.startswith("solomon-") for n in os.listdir(commands)
    )
    if has_agents and has_cmds:
        return _check("Global install", OK, "agents and /solomon commands present in ~/.claude")
    return _check(
        "Global install", WARN, "agents/commands not installed in ~/.claude",
        "Run 'solomon-harness install-global' to share them across projects.",
    )


def check_shared_home(home: Optional[str] = None) -> Dict:
    """Is the shared home (compose + assigned port) set up?"""
    home = home or harness_home()
    compose = os.path.join(home, "docker-compose.yml")
    if os.path.isfile(compose):
        return _check("Shared home", OK, f"{home} (memory port {assigned_memory_port(home)})")
    return _check(
        "Shared home", WARN, f"{home} is not initialized",
        "Run 'solomon-harness install-global' (or 'init') to set up the shared memory home.",
    )


def run_checks(workspace_root: Optional[str] = None) -> List[Dict]:
    workspace_root = workspace_root or os.getcwd()
    specs = [
        ("Docker", check_docker),
        ("Shared home", check_shared_home),
        ("Memory backend", lambda: check_memory(workspace_root)),
        ("Global install", check_global_install),
        ("GitHub auth", check_github),
    ]
    checks = []
    for label, fn in specs:
        try:
            checks.append(fn())
        except Exception as exc:  # never let a check break the report
            checks.append(_check(label, WARN, f"check failed: {exc}"))
    return checks


_SYMBOL = {OK: "ok  ", WARN: "warn", FAIL: "fail"}


def format_report(checks: List[Dict]) -> str:
    lines = ["Harness healthcheck:"]
    for c in checks:
        lines.append(f"  {_SYMBOL.get(c['status'], '?   ')}  {c['name']}: {c['detail']}")
        if c["status"] != OK and c.get("fix"):
            lines.append(f"          -> {c['fix']}")
    return "\n".join(lines)


def pending_summary(checks: List[Dict]) -> List[str]:
    """The non-ok checks as 'name: fix' lines, for a compact session-start notice."""
    out = []
    for c in checks:
        if c["status"] != OK:
            out.append(f"{c['name']}: {c.get('fix') or c['detail']}")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    checks = run_checks()
    print(format_report(checks))
    return 1 if any(c["status"] == FAIL for c in checks) else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
