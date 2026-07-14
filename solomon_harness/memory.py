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
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from typing import List, Optional, Tuple

from solomon_harness.home import assigned_memory_port, harness_home

DEFAULT_URL = "ws://localhost:8099/rpc"
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


def _tcp_open(host: str, port: int, timeout: float = 0.75) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout.

    A bare open port is not proof the right service is there: any process can
    hold the port. Use is_serving to confirm it is actually SurrealDB.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_serving(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True only if SurrealDB is actually serving on host:port.

    SurrealDB answers GET /version with its version banner (e.g.
    ``surrealdb-2.1.0``). A foreign process that merely holds the port (or
    answers /health) will not, so this is the signal we trust instead of a raw
    TCP probe.
    """
    url = f"http://{host}:{port}/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (local URL)
            if getattr(resp, "status", 200) != 200:
                return False
            body = resp.read(256).decode("utf-8", "ignore")
            return "surreal" in body.lower()
    except Exception:
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


def _packaged_compose() -> Optional[str]:
    """Path to the docker-compose.yml bundled with this package's repo, or None."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(repo_root, "docker-compose.yml")
    return candidate if os.path.isfile(candidate) else None


def _set_published_port(compose_text: str, port: int) -> str:
    """Rewrite the SurrealDB published host port in a compose file's text.

    Only the host side of the ``"<host>:8000"`` mapping changes; the container
    still listens on 8000 internally (Surrealist/Spectron reach it by service
    name). The published mapping is always pinned to the loopback interface —
    the store ships a fixed root/root development credential, so it must never
    listen on all interfaces — and a pre-loopback template (bare
    ``"<port>:8000"``) is normalized on the way through. Works whatever the
    template's current host port is.
    """
    return re.sub(r'"(?:[0-9.]+:)?\d+:8000"', f'"127.0.0.1:{port}:8000"', compose_text)


def ensure_home_compose() -> Optional[str]:
    """Ensure the shared home holds a docker-compose.yml; return its path or None.

    The memory backend is shared across all projects on the machine, so its
    compose file lives once in ``~/.solomon-harness`` rather than in each repo --
    which is what removes the per-project port collision. The SurrealDB host port
    is the one assigned for this machine (8000 when free, otherwise the next free
    port), templated into the published mapping so it never clashes with whatever
    already holds 8000 on the host.
    """
    home = harness_home()
    dest = os.path.join(home, "docker-compose.yml")
    if os.path.isfile(dest):
        return dest
    src = _packaged_compose()
    if not src:
        return None
    port = assigned_memory_port(home)
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    content = _set_published_port(content, port)
    os.makedirs(home, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return dest


def reconcile_pending(workspace_root: str) -> Optional[dict]:
    """Best-effort replay of pending write-through mirror records to SurrealDB.

    Called once the backend is confirmed up (memory-up / SessionStart) so a write
    captured locally during a prior outage is healed automatically, not only via a
    manual ``solomon-harness memory sync`` (ADR-0007, issue #35). It is bounded and
    swallowing -- it must never raise or block the session-start hook -- so any
    failure (including a backend that drops again) is reported on stderr and
    ignored. A cheap pending-count pre-check skips building a client (and opening a
    socket) when there is nothing to reconcile, which is the common case. Returns
    the reconcile counts, or None when it could not run.
    """
    try:
        from solomon_harness import healthcheck

        if healthcheck.pending_reconcile_count(workspace_root) == 0:
            return {"synced": 0, "remaining": 0}
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            return db.reconcile()
    except Exception as exc:  # never break the session-start hook
        sys.stderr.write(f"memory reconcile skipped: {exc}\n")
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

    if is_serving(host, port):
        # The backend is up: replay anything stranded by a prior outage.
        reconcile_pending(workspace_root)
        return {"ok": True, "already_running": True}

    # The port is open but it is not SurrealDB: a foreign process holds it.
    # Starting compose would fail to bind, and the client would silently fall
    # back to SQLite, so report the conflict instead of pretending it is up.
    if _tcp_open(host, port):
        return {
            "ok": False,
            "port_conflict": True,
            "error": (
                f"port {port} is held by a process that is not SurrealDB; the client "
                f"will use the SQLite fallback. Free the port (or change the configured "
                f"URL) and run 'solomon-harness memory-up' again."
            ),
        }

    compose_file = ensure_home_compose()
    if not compose_file:
        return {"ok": False, "error": "shared docker-compose.yml not found"}

    compose = _compose_command()
    if not compose:
        return {
            "ok": False,
            "error": "Docker is unavailable; memory will use the SQLite fallback.",
        }

    proc = subprocess.run(
        [*compose, "-f", compose_file, "up", "-d"],
        cwd=os.path.dirname(compose_file),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}

    # Wait for SurrealDB to actually serve (not just for the port to open) so this
    # session connects to it rather than falling back to SQLite mid-startup.
    waited = 0.0
    while waited < wait_seconds:
        if is_serving(host, port):
            # Newly serving: replay anything stranded by a prior outage.
            reconcile_pending(workspace_root)
            return {"ok": True, "started": True}
        time.sleep(1.0)
        waited += 1.0
    return {"ok": True, "started": True, "warning": "compose started; SurrealDB not serving yet"}


def stop_memory(workspace_root: Optional[str] = None) -> dict:
    """Stop the shared memory backend (docker compose down). Best-effort.

    The backend is shared across projects, so this stops it for the whole
    machine, not just one repo.
    """
    compose_file = os.path.join(harness_home(), "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return {"ok": False, "error": "shared docker-compose.yml not found"}
    compose = _compose_command()
    if not compose:
        return {"ok": False, "error": "Docker is unavailable."}
    proc = subprocess.run(
        [*compose, "-f", compose_file, "down"],
        cwd=os.path.dirname(compose_file),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    return {"ok": True, "stopped": True}


def _describe(result: dict) -> str:
    """One-line human summary of an ensure_memory_up/stop_memory result."""
    from solomon_harness.voice import say

    return say(_describe_body(result))


def _describe_body(result: dict) -> str:
    if result.get("already_running"):
        return "Memory backend already running."
    if result.get("started"):
        msg = "Memory backend started via docker compose."
        return f"{msg} ({result['warning']})" if result.get("warning") else msg
    if result.get("stopped"):
        return "Memory backend stopped."
    if result.get("skipped"):
        return f"Memory backend not managed: {result['skipped']}."
    if result.get("port_conflict"):
        return f"Memory backend not started: {result['error']}"
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
