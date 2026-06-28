"""Shared machine-wide harness home and per-project tenant resolution.

Running a SurrealDB per project collides on the backend port and duplicates the
agent definitions in every repo. Instead the harness keeps one shared home --
``~/.solomon-harness`` by default, overridable with ``SOLOMON_HARNESS_HOME`` --
that holds the single ``docker-compose.yml`` for the memory backend (and the
canonical agent sources). Each project is a tenant: its memory lives in its own
SurrealDB database, named from the git remote, inside the shared ``solomon``
namespace. One backend, no port conflicts, isolated memory per project.
"""

import hashlib
import json
import os
import re
import socket
import subprocess
from typing import Optional

DEFAULT_HOME = "~/.solomon-harness"
# 8000 (SurrealDB's own default) is heavily contended on developer machines, so
# the shared backend prefers 8099 and falls back to the next free port.
DEFAULT_MEMORY_PORT = 8099
MEMORY_CONFIG = "memory.json"


def harness_home() -> str:
    """Return the shared harness home directory (absolute). Callers create it."""
    raw = os.environ.get("SOLOMON_HARNESS_HOME", DEFAULT_HOME)
    return os.path.abspath(os.path.expanduser(raw))


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if the TCP port can be bound (i.e. nothing is holding it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(preferred: int = DEFAULT_MEMORY_PORT, limit: int = 64) -> int:
    """Return ``preferred`` if it is free, else the next free port above it.

    Bounded by ``limit`` so it never loops forever; if nothing is free in range
    it returns ``preferred`` and the caller's conflict check handles it.
    """
    for candidate in range(preferred, preferred + limit):
        if _port_free(candidate):
            return candidate
    return preferred


def assigned_memory_port(home: Optional[str] = None, preferred: int = DEFAULT_MEMORY_PORT) -> int:
    """Return the shared memory host port, assigning a free one on first use.

    The choice is recorded in ``<home>/memory.json`` and reused thereafter, so
    every project on the machine connects to the same shared SurrealDB. The port
    is only auto-assigned once; an already-running backend keeps its port instead
    of being moved.
    """
    home = home or harness_home()
    cfg = os.path.join(home, MEMORY_CONFIG)
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                return int(json.load(f).get("host_port", preferred))
        except Exception:
            pass
    port = find_free_port(preferred)
    os.makedirs(home, exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"host_port": port}, f, indent=2)
    return port


def _clean_git_env() -> dict:
    """Return the environment with all ``GIT_*`` variables removed.

    Inside a git worktree or a git hook, ``GIT_DIR`` / ``GIT_WORK_TREE`` (and
    friends) are exported and would redirect a ``git -C <other>`` call back to the
    enclosing repository. Stripping them makes git resolve the repo from the given
    working directory, so tenant resolution stays correct in worktrees and hooks.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git_remote(workspace_root: str) -> Optional[str]:
    """Return the origin remote URL of the repo, or None."""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=workspace_root,
            stderr=subprocess.DEVNULL,
            text=True,
            env=_clean_git_env(),
        ).strip()
        return out or None
    except Exception:
        return None


def _sanitize_tenant(name: str) -> str:
    """Lowercase and reduce to a safe SurrealDB database name.

    Keeps [a-z0-9_-], collapses repeats, trims separators, and caps the length.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-_")
    return s[:60] or "project"


def slug_from_remote(remote: str) -> Optional[str]:
    """Turn a git remote URL into an ``owner-repo`` slug, or None if unparseable.

    Handles the scp form (``git@github.com:ortisan/solomon-harness.git``) and the
    URL form (``https://github.com/ortisan/solomon-harness.git``); both yield
    ``ortisan-solomon-harness``.
    """
    r = remote.strip()
    r = re.sub(r"\.git/?$", "", r)
    if "://" in r:  # scheme://host/owner/repo
        r = r.split("://", 1)[1]
        r = r.split("/", 1)[1] if "/" in r else r
    elif "@" in r and ":" in r:  # user@host:owner/repo
        r = r.split(":", 1)[1]
    parts = [p for p in re.split(r"[/:]", r) if p]
    if not parts:
        return None
    tail = parts[-2:] if len(parts) >= 2 else parts[-1:]
    return _sanitize_tenant("-".join(tail))


def derive_tenant(workspace_root: str) -> str:
    """Return the per-project tenant id (used as the SurrealDB database name).

    Primary: the git remote slug (``owner-repo``). Fallback for remote-less
    repos: the directory name plus a short hash of the absolute path, so two
    same-named projects never collide.
    """
    remote = _git_remote(workspace_root)
    if remote:
        slug = slug_from_remote(remote)
        if slug:
            return slug
    base = os.path.basename(os.path.abspath(workspace_root)) or "project"
    digest = hashlib.sha1(os.path.abspath(workspace_root).encode("utf-8")).hexdigest()[:6]
    return _sanitize_tenant(f"{base}-{digest}")
