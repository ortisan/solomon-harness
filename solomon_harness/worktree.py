"""Idempotent git worktree creation for /solomon-start.

The start stage runs each issue in its own isolated worktree, so beginning a new
issue never disturbs the primary checkout or another in-flight issue. This module
owns the worktree contract: where the worktree lives, how it is created or reused,
and how conflicts are reported.

Layout (decided in issue #8): a sibling root beside the primary checkout,
``<parent>/<name>-worktrees/<branch-with-slashes-as-dashes>``, never nested inside
the repository. A nested second working tree would be double-traversed by
recursive tooling that ignores ``.gitignore`` (pytest collection, file watchers,
IDE indexers); the sibling layout keeps it out of the primary checkout entirely.
"""

import os
import re
import subprocess
import sys
from typing import List, Optional, Tuple

# Conservative ref grammar: git ref characters we are willing to place on the
# command line and in a filesystem path. Path traversal, control characters, and
# option-injection are rejected before the value reaches subprocess or os.path.
# Matched via re.fullmatch so a trailing newline (which "$" would tolerate) is
# rejected.
_REF_RE = re.compile(r"[A-Za-z0-9._/-]+")

# Directory/index redirectors git sets while a hook runs. Inherited into a
# subprocess they override ``git -C <path>`` and point every command back at the
# outer repository, so we strip them before shelling out. This keeps the helper
# correct when it (or its tests) runs inside a git hook.
_GIT_REDIRECT_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def _clean_git_env() -> dict:
    env = dict(os.environ)
    for key in _GIT_REDIRECT_ENV:
        env.pop(key, None)
    return env


class WorktreeError(Exception):
    """Base error for worktree operations."""


class WorktreeConflict(WorktreeError):
    """A worktree could not be created without forcing over existing state."""


def _run_git(repo_root: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        text=True,
        check=False,
        env=_clean_git_env(),
    )
    if check and proc.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _validate_ref(value: str, label: str) -> None:
    if (
        not value
        or value.startswith("-")
        or value.startswith("/")
        or ".." in value
        or any(ord(ch) < 0x20 for ch in value)
        or not _REF_RE.fullmatch(value)
    ):
        raise WorktreeError(f"invalid {label}: {value!r}")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise WorktreeError(f"invalid {label}: {value!r}")


def _validate_branch(branch: str) -> None:
    _validate_ref(branch, "branch name")


def repo_toplevel(repo_root: str) -> str:
    """Return the absolute top-level path of the repository at ``repo_root``."""
    return _run_git(repo_root, ["rev-parse", "--show-toplevel"]).stdout.strip()


def _main_worktree(repo_root: str) -> str:
    """Absolute path of the repository's main worktree (git lists it first), so the
    sibling root is the same whether this is called from the primary checkout or
    from inside a linked worktree."""
    entries = _list_worktrees(repo_root)
    if entries:
        return entries[0][0]
    return os.path.realpath(repo_toplevel(repo_root))


def worktree_root(repo_root: str) -> str:
    """Return the sibling worktree root ``<parent>/<name>-worktrees``, anchored on
    the main worktree so it does not depend on the caller's current directory."""
    main = _main_worktree(repo_root)
    return os.path.join(os.path.dirname(main), f"{os.path.basename(main)}-worktrees")


def worktree_path(repo_root: str, branch: str) -> str:
    """Return the absolute worktree path for ``branch`` under the sibling root."""
    _validate_branch(branch)
    return os.path.join(worktree_root(repo_root), branch.replace("/", "-"))


def _list_worktrees(repo_root: str) -> List[Tuple[str, Optional[str]]]:
    """Return ``(realpath, branch)`` for every registered worktree."""
    out = _run_git(repo_root, ["worktree", "list", "--porcelain"]).stdout
    entries: List[Tuple[str, Optional[str]]] = []
    path: Optional[str] = None
    branch: Optional[str] = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
            branch = None
        elif line.startswith("branch "):
            branch = line[len("branch ") :].replace("refs/heads/", "", 1)
        elif line == "" and path is not None:
            entries.append((os.path.realpath(path), branch))
            path = None
            branch = None
    if path is not None:
        entries.append((os.path.realpath(path), branch))
    return entries


def _branch_exists(repo_root: str, branch: str) -> bool:
    proc = _run_git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    )
    return proc.returncode == 0


def ensure_worktree(repo_root: str, branch: str, base: str = "develop") -> str:
    """Create or locate the worktree for ``branch``; return its absolute path.

    Idempotent: when the worktree already exists on the expected branch, no
    ``git worktree add`` runs and the existing path is returned. Raises
    :class:`WorktreeConflict` when the target path is occupied by something other
    than the expected worktree, or when the branch is already checked out in a
    different worktree. No partial worktree is left behind on conflict.
    """
    _validate_branch(branch)
    # base reaches the git command line as a positional commit-ish; validate it
    # with the same allowlist so an option-shaped value (e.g. "--force") cannot be
    # parsed as a flag and defeat the conflict checks below.
    _validate_ref(base, "base ref")
    target = os.path.realpath(worktree_path(repo_root, branch))
    existing = _list_worktrees(repo_root)
    by_path = dict(existing)

    # Idempotent reuse: the worktree is already there on the expected branch.
    if target in by_path:
        if by_path[target] == branch:
            return target
        raise WorktreeConflict(
            f"path {target} is already a worktree on branch "
            f"'{by_path[target]}', not '{branch}'"
        )

    # The branch is checked out somewhere other than its computed path.
    for path, head in existing:
        if head == branch and path != target:
            raise WorktreeConflict(
                f"branch '{branch}' is already checked out in another worktree at {path}"
            )

    # The computed path is taken by a directory git does not manage.
    if os.path.exists(target):
        raise WorktreeConflict(
            f"path {target} already exists and is not a registered worktree"
        )

    os.makedirs(os.path.dirname(target), exist_ok=True)
    if _branch_exists(repo_root, branch):
        add_args = ["worktree", "add", target, branch]
    else:
        add_args = ["worktree", "add", "-b", branch, target, base]
    proc = _run_git(repo_root, add_args, check=False)
    if proc.returncode != 0:
        raise WorktreeConflict(
            f"could not create worktree for '{branch}' at {target}: {proc.stderr.strip()}"
        )
    return target


def cli_worktree(repo_root: str, branch: str, base: str = "develop") -> int:
    """CLI wrapper: print the worktree path (exit 0) or a diagnostic (non-zero)."""
    try:
        path = ensure_worktree(repo_root, branch, base=base)
    except WorktreeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0
