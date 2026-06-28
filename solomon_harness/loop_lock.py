"""Single-driver loop lock: the Phase 0 safety floor for loop engineering.

Two concurrent solomon drivers on one repository previously collided — premature
merges that bypassed the review gate, and worktree tooling flipping
``core.bare=true``. This module makes that race impossible by construction: every
driver acquires one advisory lockfile before it touches git or the board, and a
second driver is refused.

The lock is anchored at the git *common* directory (resolved by reading ``.git``
directly, not by shelling out to ``git`` — which would be intercepted by tests
that patch ``subprocess.run``), so all linked worktrees of a repository contend
on the same file. When the directory is not a git repository the lock falls back
to ``<root>/.solomon/loop.lock``.

The lock is a plain JSON file on disk, so the holder is itself auditable —
"every decision traces back to a file on disk". Staleness is reclaimable: a lock
whose heartbeat is older than the TTL, or whose pid is dead on the same host, is
taken over by the next driver rather than wedging the loop forever.
"""

import json
import os
import re
import socket
import time
from typing import Any, Callable, Dict, Optional, Tuple

DEFAULT_TTL_SECONDS = 1800.0
LOCK_FILENAME_GIT = "solomon-loop.lock"
LOCK_RELPATH_FALLBACK = os.path.join(".solomon", "loop.lock")


class LoopLockHeld(Exception):
    """Raised when acquiring a lock another live driver already holds."""

    def __init__(self, holder: Dict[str, Any]):
        self.holder = holder
        who = holder.get("session_id", "?")
        since = holder.get("acquired_at", "?")
        super().__init__(
            f"loop lock held by session {who} (pid {holder.get('pid')}) since {since}"
        )


def _find_repo_dir(start: str) -> Optional[str]:
    """Return the nearest ancestor of ``start`` that contains a ``.git`` entry."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _read_gitdir(dotgit_file: str, worktree_root: str) -> Optional[str]:
    """Parse ``gitdir: <path>`` from a linked-worktree ``.git`` file."""
    try:
        with open(dotgit_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("gitdir:"):
                    gitdir = line.split(":", 1)[1].strip()
                    if not os.path.isabs(gitdir):
                        gitdir = os.path.join(worktree_root, gitdir)
                    return os.path.normpath(gitdir)
    except OSError:
        return None
    return None


def resolve_lock_path(workspace_root: str) -> str:
    """Resolve the lockfile path, anchored at the git common dir when possible."""
    repo = _find_repo_dir(workspace_root)
    if repo is None:
        return os.path.join(os.path.abspath(workspace_root), LOCK_RELPATH_FALLBACK)

    dotgit = os.path.join(repo, ".git")
    if os.path.isdir(dotgit):
        common = dotgit
    elif os.path.isfile(dotgit):
        gitdir = _read_gitdir(dotgit, repo)
        marker = os.sep + "worktrees" + os.sep
        if gitdir and marker in gitdir:
            common = gitdir.split(marker)[0]
        elif gitdir:
            common = gitdir
        else:
            common = dotgit
    else:  # pragma: no cover - defensive
        return os.path.join(os.path.abspath(workspace_root), LOCK_RELPATH_FALLBACK)
    return os.path.join(common, LOCK_FILENAME_GIT)


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check for a pid on the local host."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except OSError:
        return True
    return True


class LoopLock:
    """An advisory, reclaimable, single-driver lock backed by one JSON file."""

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        *,
        lock_path: Optional[str] = None,
        session_id: Optional[str] = None,
        pid: Optional[int] = None,
        host: Optional[str] = None,
        stage: Optional[str] = None,
        ttl: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
        pid_alive: Callable[[int], bool] = _pid_alive,
    ) -> None:
        if lock_path is None:
            if workspace_root is None:
                raise ValueError("LoopLock needs a workspace_root or an explicit lock_path")
            lock_path = resolve_lock_path(workspace_root)
        self.path = lock_path
        self.host = host or socket.gethostname()
        self.pid = pid if pid is not None else os.getpid()
        self.session_id = session_id or os.environ.get(
            "SOLOMON_SESSION_ID", os.environ.get("CLAUDE_SESSION_ID", f"{self.host}:{self.pid}")
        )
        self.stage = stage
        self.ttl = float(ttl)
        self._clock = clock
        self._pid_alive = pid_alive

    # -- inspection ---------------------------------------------------------
    def read(self) -> Optional[Dict[str, Any]]:
        """Return the current lock contents, or None if no lockfile exists."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def is_stale(self, info: Dict[str, Any]) -> bool:
        """A lock is stale past its TTL, or with a dead pid on the same host."""
        beat = info.get("heartbeat_at") or info.get("acquired_at")
        ts = _parse_epoch(beat)
        if ts is None or (self._clock() - ts) > self.ttl:
            return True
        if info.get("host") == self.host and info.get("pid") is not None:
            try:
                if not self._pid_alive(int(info["pid"])):
                    return True
            except (TypeError, ValueError):
                pass
        return False

    def held_by_other(self) -> Optional[Dict[str, Any]]:
        """Return the holder if a *live* lock owned by another session exists."""
        info = self.read()
        if not info:
            return None
        if info.get("session_id") == self.session_id:
            return None
        if self.is_stale(info):
            return None
        return info

    # -- mutation -----------------------------------------------------------
    def _body(self, now: float, acquired_at: Optional[float] = None) -> str:
        acq = acquired_at if acquired_at is not None else now
        return json.dumps(
            {
                "session_id": self.session_id,
                "pid": self.pid,
                "host": self.host,
                "stage": self.stage,
                "acquired_at": _iso(acq),
                "heartbeat_at": _iso(now),
            }
        )

    def _write_atomically(self, now: float) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.{self.pid}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self._body(now))
        os.replace(tmp, self.path)

    def acquire(self, stage: Optional[str] = None) -> "LoopLock":
        """Acquire the lock, reclaiming a stale one; raise LoopLockHeld if live."""
        if stage is not None:
            self.stage = stage
        now = self._clock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            info = self.read()
            if info and info.get("session_id") == self.session_id:
                self._write_atomically(now)  # re-entrant: refresh heartbeat
                return self
            if info and not self.is_stale(info):
                raise LoopLockHeld(info)
            # Stale or unreadable: reclaim by overwriting atomically.
            self._write_atomically(now)
            return self
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self._body(now))
            return self

    def heartbeat(self) -> None:
        """Refresh the heartbeat if this session still owns the lock."""
        info = self.read()
        if info and info.get("session_id") == self.session_id:
            self._write_atomically(self._clock())

    def release(self) -> None:
        """Remove the lockfile only if this session owns it (or it is stale)."""
        info = self.read()
        if info is None:
            return
        if info.get("session_id") == self.session_id or self.is_stale(info):
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "LoopLock":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


_PUSH_OR_MERGE = re.compile(r"\b(git\s+push|gh\s+pr\s+merge|git\s+merge)\b")


def is_push_or_merge(command: str) -> bool:
    """True when a shell command pushes or merges (the irreversible operations)."""
    return bool(_PUSH_OR_MERGE.search(command or ""))


def guard_verdict(payload: Dict[str, Any], lock: "LoopLock") -> Tuple[bool, str]:
    """Decide whether a PreToolUse Bash command must be blocked.

    Block only a push/merge issued while another live driver holds the loop lock.
    This is the Claude-only defense-in-depth layer; the portable enforcement that
    works on both hosts is the gate inside ``run_stage``. Fail-open by default:
    anything not clearly a push/merge under a live foreign lock is allowed.
    """
    if (payload.get("tool_name") or payload.get("tool") or "") != "Bash":
        return (False, "")
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or payload.get("command") or ""
    if not is_push_or_merge(command):
        return (False, "")
    holder = lock.held_by_other()
    if not holder:
        return (False, "")
    reason = (
        f"Blocked by the solomon single-driver lock: another driver (session "
        f"{holder.get('session_id')}, pid {holder.get('pid')}) is running. The command "
        f"{command!r} could merge or push outside the review gate. Wait for it to "
        "finish, or clear a stale lock with 'solomon-harness loop-lock release'."
    )
    return (True, reason)


def _iso(epoch: float) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).isoformat()


def _parse_epoch(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        import datetime

        s = str(value).replace(" ", "T").rstrip("Z")
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None
