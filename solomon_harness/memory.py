"""Bring the project memory backend (SurrealDB via docker compose) up on demand.

The SessionStart hook calls ``ensure_memory_up`` so the SurrealDB store defined
in ``docker-compose.yml`` is running before the harness reads or writes memory.
It is best-effort and idempotent: if the backend is already reachable it does
nothing, and if Docker is absent or the compose file is missing it degrades to a
message. The client falls back to a local SQLite store in that case, so a
developer without Docker is never blocked.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from typing import List, Optional, Tuple

DEFAULT_URL = "ws://localhost:8000/rpc"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


def _read_db_url(workspace_root: str) -> Tuple[str, str]:
    """Return (provider, url) from the workspace .agent/config.json, with defaults.

    Environment overrides (SURREAL_URL) win, matching the database client.
    """
    provider = "surrealdb"
    url = DEFAULT_URL
    config_path = os.path.join(workspace_root, ".agent", "config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                db = (json.load(f) or {}).get("database", {}) or {}
            provider = db.get("provider", provider)
            url = db.get("url", url)
        except Exception:
            pass
    return provider, os.environ.get("SURREAL_URL", url)


def _host_port(url: str, default_port: int = 8000) -> Tuple[str, int]:
    """Parse host and port from a ws(s):// URL like ws://localhost:8000/rpc."""
    authority = url.split("://", 1)[-1].split("/", 1)[0]
    if ":" in authority:
        host, _, port = authority.partition(":")
        try:
            return host or "localhost", int(port)
        except ValueError:
            return host or "localhost", default_port
    return authority or "localhost", default_port


def is_reachable(host: str, port: int, timeout: float = 0.75) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _compose_command() -> Optional[List[str]]:
    """Return the available docker compose invocation, or None if Docker is absent."""
    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def ensure_memory_up(
    workspace_root: Optional[str] = None, wait_seconds: int = 25
) -> dict:
    """Start the memory backend via docker compose if it is not already reachable.

    Best-effort and idempotent. Returns a result dict and never raises. The work
    is skipped when the backend is already reachable, when the configured backend
    is not a local SurrealDB, when the compose file is missing, or when Docker is
    unavailable.
    """
    workspace_root = workspace_root or os.getcwd()
    provider, url = _read_db_url(workspace_root)
    if provider != "surrealdb":
        return {"ok": True, "skipped": "backend is not surrealdb"}

    host, port = _host_port(url)
    if host not in LOCAL_HOSTS:
        return {"ok": True, "skipped": f"backend host '{host}' is not local"}

    if is_reachable(host, port):
        return {"ok": True, "already_running": True}

    compose_file = os.path.join(workspace_root, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return {"ok": False, "error": "docker-compose.yml not found"}

    compose = _compose_command()
    if not compose:
        return {
            "ok": False,
            "error": "Docker is unavailable; memory will use the SQLite fallback.",
        }

    proc = subprocess.run(
        [*compose, "-f", compose_file, "up", "-d"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}

    # Wait briefly for the port so this session connects to SurrealDB rather than
    # falling back to SQLite while the container is still starting.
    waited = 0.0
    while waited < wait_seconds:
        if is_reachable(host, port):
            return {"ok": True, "started": True}
        time.sleep(1.0)
        waited += 1.0
    return {"ok": True, "started": True, "warning": "compose started; not reachable yet"}


def stop_memory(workspace_root: Optional[str] = None) -> dict:
    """Stop the memory backend (docker compose down). Best-effort."""
    workspace_root = workspace_root or os.getcwd()
    compose_file = os.path.join(workspace_root, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return {"ok": False, "error": "docker-compose.yml not found"}
    compose = _compose_command()
    if not compose:
        return {"ok": False, "error": "Docker is unavailable."}
    proc = subprocess.run(
        [*compose, "-f", compose_file, "down"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    return {"ok": True, "stopped": True}


def _describe(result: dict) -> str:
    """One-line human summary of an ensure_memory_up/stop_memory result."""
    if result.get("already_running"):
        return "Memory backend already running."
    if result.get("started"):
        msg = "Memory backend started via docker compose."
        return f"{msg} ({result['warning']})" if result.get("warning") else msg
    if result.get("stopped"):
        return "Memory backend stopped."
    if result.get("skipped"):
        return f"Memory backend not managed: {result['skipped']}."
    return result.get("error", "Memory backend: unknown state.")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    action = argv[0] if argv else "up"
    if action == "down":
        result = stop_memory()
    else:
        result = ensure_memory_up()
    print(_describe(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
