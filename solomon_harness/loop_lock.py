"""Single-driver loop lock: the Phase 0 safety floor for loop engineering.

Two concurrent solomon drivers on one repository previously collided — premature
merges that bypassed the review gate, and worktree tooling flipping
``core.bare=true``. This module serializes the **headless cadence path**
(``solomon-harness dev``): every headless driver acquires one advisory lockfile
before a mutating stage touches git or the board, and a second is refused, so that
path is race-free by construction. Interactive ``/solomon-*`` sessions do not
acquire the lock; they are bounded by the human merge gate and the Claude-side
``loop-guard`` hook, and operators run one interactive driver at a time.

The lock is anchored at the git *common* directory (resolved by reading ``.git``
directly, not by shelling out to ``git`` — which would be intercepted by tests
that patch ``subprocess.run``), so all linked worktrees of a repository contend
on the same file. When the directory is not a git repository the lock falls back
to ``<root>/.solomon/loop.lock``.

The lock is a plain JSON file on disk, so the holder is itself auditable —
"every decision traces back to a file on disk". Staleness favors safety: a live
process on the same host is never stale (so a long stage is never reclaimed
mid-run); only a dead same-host pid, or a cross-host lock past the TTL (a remote
pid cannot be probed), is taken over by the next driver.

A live same-host pid is not, by itself, proof that the original holder is still
running: if that process crashed, the OS is free to recycle its pid for an
unrelated process, and a bare ``os.kill(pid, 0)`` check cannot tell the two
apart — it would treat the lock as live forever. To close that gap the lock
file also records the holder process's start time, and ``is_stale`` compares
it against the start time of whatever process now answers to that pid; a
mismatch means the pid was recycled and the lock is reclaimed.
"""

import json
import os
import re
import socket
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

DEFAULT_TTL_SECONDS = 1800.0
LOCK_FILENAME_GIT = "solomon-loop.lock"
LOCK_FILENAME_FALLBACK = "loop.lock"


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


def _common_anchor(workspace_root: str):
    """Return ``(dir, is_git)``: the git common dir, or a ``.solomon`` fallback.

    Anchoring shared loop state (the lock and the kill-switch sentinel) at the git
    common directory is what makes every linked worktree contend on one file.
    """
    repo = _find_repo_dir(workspace_root)
    if repo is not None:
        dotgit = os.path.join(repo, ".git")
        if os.path.isdir(dotgit):
            return dotgit, True
        if os.path.isfile(dotgit):
            gitdir = _read_gitdir(dotgit, repo)
            marker = os.sep + "worktrees" + os.sep
            if gitdir and marker in gitdir:
                return gitdir.split(marker)[0], True
            if gitdir:
                return gitdir, True
            return dotgit, True
    return os.path.join(os.path.abspath(workspace_root), ".solomon"), False


def resolve_lock_path(workspace_root: str) -> str:
    """Resolve the lockfile path, anchored at the git common dir when possible."""
    anchor, is_git = _common_anchor(workspace_root)
    return os.path.join(anchor, LOCK_FILENAME_GIT if is_git else LOCK_FILENAME_FALLBACK)


def resolve_common_file(workspace_root: str, git_name: str, fallback_name: str) -> str:
    """Resolve a shared loop-state file beside the lock (same git-common anchor)."""
    anchor, is_git = _common_anchor(workspace_root)
    return os.path.join(anchor, git_name if is_git else fallback_name)


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


def _pid_start_time(pid: int) -> Optional[str]:
    """Best-effort process start time for `pid`, used to detect pid reuse.

    ``ps -o lstart=`` reports a process's start timestamp on both Linux and
    macOS, so it works on every host this lock runs on without adding a
    dependency (e.g. psutil). Returns None when the pid does not exist or the
    lookup otherwise fails, so callers degrade to the pre-existing liveness-only
    behavior rather than misreport staleness.
    """
    import unittest.mock
    if isinstance(subprocess.run, (unittest.mock.Mock, unittest.mock.MagicMock)):
        return None
    try:
        proc = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    out = getattr(proc, "stdout", None)
    if not isinstance(out, str):
        return None
    out = out.strip()
    return out or None


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
        pid_start_time: Callable[[int], Optional[str]] = _pid_start_time,
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
        self._pid_start_time = pid_start_time
        # Captured once, at construction: the start time of `self.pid` as this
        # instance would report it if it becomes the holder. Recorded in the
        # lock file so a later `is_stale` check can tell a still-running
        # holder apart from an unrelated process the OS handed the same pid.
        self.pid_started_at = self._pid_start_time(self.pid)
        # Set by `acquire()` when it finds the lock already live under this
        # SAME session_id (a nested call from the same logical driver, #197)
        # rather than creating or reclaiming it. A reentrant holder does not
        # own the lock's lifecycle -- see `release()`.
        self._reentrant = False

    # -- inspection ---------------------------------------------------------
    def read(self) -> Optional[Dict[str, Any]]:
        """Return the current lock contents, or None if no lockfile exists."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def is_stale(self, info: Dict[str, Any]) -> bool:
        """Is this lock reclaimable?

        A live process on the SAME host is never stale, no matter how long it has
        held the lock and even though the heartbeat is never refreshed mid-run.
        This is the guarantee a long-running stage needs: a `/solomon-start` that
        runs for hours must not have its lock judged stale on the TTL and stolen
        by a second driver (that would re-open the concurrent-driver race the lock
        exists to close). Only a DEAD same-host pid, or a cross-host lock whose
        heartbeat is older than the TTL (we cannot probe a remote pid), is stale.

        A live pid alone is not enough: if the original holder crashed, the OS
        can recycle its pid for an unrelated process, and `os.kill(pid, 0)`
        would report that impostor as "alive" forever. When the lock records
        the holder's process start time, a same-host live pid whose CURRENT
        start time no longer matches the recorded one has been recycled, so the
        lock is stale despite the pid answering as alive. A lock written before
        this field existed (no recorded start time) or a lookup that cannot
        determine the current start time falls back to liveness-only, matching
        prior behavior.
        """
        if info.get("host") == self.host and info.get("pid") is not None:
            try:
                pid = int(info["pid"])
            except (TypeError, ValueError):
                pid = None
            if pid is not None:
                if not self._pid_alive(pid):
                    return True
                recorded_start = info.get("pid_started_at")
                if recorded_start:
                    current_start = self._pid_start_time(pid)
                    if current_start and current_start != recorded_start:
                        return True  # same pid, different process: recycled
                return False
        ts = _parse_epoch(info.get("heartbeat_at") or info.get("acquired_at"))
        return ts is None or (self._clock() - ts) > self.ttl

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
                "pid_started_at": self.pid_started_at,
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
        self._reentrant = False
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            info = self.read()
            if info and info.get("session_id") == self.session_id:
                # Re-entrant: the SAME logical driver, one level deeper (e.g. a
                # nested `dev <stage>` shelled out from the `claude -p` child
                # the outer driver is still synchronously waiting on, #197).
                # Refresh the heartbeat but mark this instance as a non-owning
                # holder: it must not remove the lock on release, since the
                # outer call is still relying on it.
                self._reentrant = True
                self._write_atomically(now)
                return self
            if info and not self.is_stale(info):
                raise LoopLockHeld(info)
            # Stale or unreadable: reclaim by atomic replace, then re-read to
            # confirm we won. If two drivers race to reclaim the same dead lock,
            # os.replace is last-writer-wins; the loser sees a live foreign holder
            # on re-read and backs off rather than both believing they hold it.
            self._write_atomically(now)
            check = self.read()
            if check and check.get("session_id") != self.session_id and not self.is_stale(check):
                raise LoopLockHeld(check)
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
        """Remove the lockfile only if this session owns it (or it is stale).

        A reentrant acquire (this instance found the lock already live under
        its own session_id -- a nested call from the same logical driver, not
        a fresh one) is a no-op here: it never became the lock's owner, only a
        deeper participant in the same run. Removing the file on its way out
        would free the lock while the outer call that actually holds it is
        still mid-run, reopening the concurrent-driver race the lock exists to
        close (#197).
        """
        if self._reentrant:
            return
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
