"""Canonical repository-local paths for an installed Solomon harness.

The installed layout has one writable home, ``.agents/solomon``.  Host
discovery files remain at their native locations, but runtime code must resolve
canonical content through :class:`HarnessPaths` instead of repeating path
literals.  Read-side resolvers retain the legacy root layout for one migration
window; their default, and every new write target, is the canonical path.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


PathLike = Union[str, os.PathLike[str]]


class PathConfinementError(ValueError):
    """Raised when a path leaves its trust boundary or traverses a symlink."""


def _absolute(path: PathLike) -> Path:
    """Return a lexical absolute path without requiring it to exist.

    Workspace discovery must preserve the path spelling supplied by callers.
    On macOS, resolving ``/var`` to ``/private/var`` breaks CLI and sandbox
    path contracts even though both names identify the same directory.  The
    security boundaries that follow links use ``Path.resolve`` explicitly at
    the point where confinement is checked.
    """

    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _confined_path(root: PathLike, target: PathLike, *, operation: str) -> Path:
    """Return a path confined below ``root`` without traversing symlinks."""

    workspace = _absolute(root)
    candidate = Path(target).expanduser()
    if ".." in candidate.parts:
        raise PathConfinementError(
            f"{operation} path contains parent traversal: {target}"
        )
    destination = _absolute(candidate) if candidate.is_absolute() else workspace / candidate
    try:
        destination.relative_to(workspace)
    except ValueError as exc:
        raise PathConfinementError(
            f"{operation} path escapes boundary {workspace}: {destination}"
        ) from exc

    cursor = destination
    while cursor != workspace:
        if cursor.is_symlink():
            raise PathConfinementError(
                f"{operation} path traverses a symlink: {destination}"
            )
        parent = cursor.parent
        if parent == cursor:
            raise PathConfinementError(
                f"{operation} path escapes boundary {workspace}: {destination}"
            )
        cursor = parent

    try:
        destination.parent.resolve().relative_to(workspace.resolve())
    except ValueError as exc:
        raise PathConfinementError(
            f"{operation} path resolves outside boundary {workspace}: {destination}"
        ) from exc
    return destination


def confined_path(root: PathLike, target: PathLike) -> Path:
    """Return a workspace-confined write path, rejecting every nested symlink.

    ``target`` may be repository-relative or absolute.  The repository root may
    itself use an OS alias (for example macOS ``/var``); only descendants from
    that declared root to the target are forbidden from traversing symlinks.
    """

    return _confined_path(root, target, operation="write")


def confined_read_path(root: PathLike, target: PathLike) -> Path:
    """Return a read path confined below ``root`` without following symlinks.

    The target need not exist. Callers can therefore validate every ordered
    compatibility candidate before deciding whether it is usable, preventing a
    symlinked canonical path from silently falling through to legacy content.
    """

    return _confined_path(root, target, operation="read")


def _preferred_path(candidates: Iterable[Path], *, directory: bool) -> Path:
    """Return the canonical path, or the first usable legacy fallback.

    A present canonical path wins even when it has the wrong type.  Returning
    that path makes a malformed new installation fail at its consumer instead
    of silently reading stale legacy state.  Legacy candidates are considered
    only while the canonical target is absent.
    """

    ordered = tuple(candidates)
    if not ordered:
        raise ValueError("at least one path candidate is required")

    canonical = ordered[0]
    if canonical.exists():
        return canonical

    predicate = Path.is_dir if directory else Path.is_file
    for candidate in ordered[1:]:
        if predicate(candidate):
            return candidate
    return canonical


@dataclass(frozen=True)
class HarnessPaths:
    """Path contract for one consumer repository.

    Properties name write targets.  ``resolve_*`` methods are read-side
    compatibility helpers: they prefer an existing canonical target, fall back
    to the matching legacy location, and return the canonical target when
    neither exists.
    """

    root: Path

    def __init__(self, root: PathLike) -> None:
        object.__setattr__(self, "root", _absolute(root))

    # -- canonical core -------------------------------------------------
    @property
    def agents_root(self) -> Path:
        return self.root / ".agents"

    @property
    def solomon(self) -> Path:
        return self.agents_root / "solomon"

    @property
    def manifest(self) -> Path:
        return self.solomon / "manifest.json"

    @property
    def config_dir(self) -> Path:
        return self.solomon / "config"

    @property
    def config(self) -> Path:
        return self.config_dir / "project.json"

    @property
    def rules(self) -> Path:
        return self.solomon / "AGENTS.md"

    @property
    def agents(self) -> Path:
        return self.solomon / "agents"

    @property
    def workflows(self) -> Path:
        return self.solomon / "workflows"

    @property
    def conventions(self) -> Path:
        return self.solomon / "conventions"

    @property
    def scripts(self) -> Path:
        return self.solomon / "scripts"

    @property
    def python_package(self) -> Path:
        return self.solomon / "solomon_harness"

    @property
    def pyproject(self) -> Path:
        return self.solomon / "pyproject.toml"

    @property
    def lockfile(self) -> Path:
        return self.solomon / "uv.lock"

    @property
    def skill_sources(self) -> Path:
        return self.solomon / "skill-sources.json"

    @property
    def state(self) -> Path:
        return self.solomon / "state"

    @property
    def memory(self) -> Path:
        return self.state / "memory"

    @property
    def sqlite_database(self) -> Path:
        return self.memory / "long_term" / "harness.db"

    @property
    def handoffs(self) -> Path:
        return self.state / "handoffs"

    @property
    def previous_handoffs(self) -> Path:
        """Pre-240 canonical location retained as a one-release read fallback."""

        return self.solomon / "handoffs"

    # -- shared AGY/Codex discovery ------------------------------------
    @property
    def shared_skills(self) -> Path:
        return self.agents_root / "skills"

    @property
    def agy_hooks(self) -> Path:
        return self.agents_root / "hooks.json"

    @property
    def agy_mcp(self) -> Path:
        return self.agy_plugins / "mcp_config.json"

    @property
    def agy_plugins(self) -> Path:
        return self.agents_root / "plugins" / "solomon"

    # -- fixed host discovery bridges ----------------------------------
    @property
    def root_instructions(self) -> Path:
        return self.root / "AGENTS.md"

    @property
    def claude_dir(self) -> Path:
        return self.root / ".claude"

    @property
    def claude_instructions(self) -> Path:
        return self.claude_dir / "CLAUDE.md"

    @property
    def claude_settings(self) -> Path:
        return self.claude_dir / "settings.json"

    @property
    def claude_agents(self) -> Path:
        return self.claude_dir / "agents"

    @property
    def claude_skills(self) -> Path:
        return self.claude_dir / "skills"

    @property
    def claude_mcp(self) -> Path:
        return self.root / ".mcp.json"

    @property
    def codex_dir(self) -> Path:
        return self.root / ".codex"

    @property
    def codex_config(self) -> Path:
        return self.codex_dir / "config.toml"

    @property
    def codex_hooks(self) -> Path:
        return self.codex_dir / "hooks.json"

    @property
    def codex_agents(self) -> Path:
        return self.codex_dir / "agents"

    # -- legacy read locations -----------------------------------------
    @property
    def legacy_config(self) -> Path:
        return self.root / ".agent" / "config.json"

    @property
    def legacy_state(self) -> Path:
        return self.root / ".solomon"

    @property
    def legacy_memory(self) -> Path:
        """Pre-layout runtime state used by releases before ADR-0036."""

        return self.root / "memory"

    @property
    def legacy_sqlite_database(self) -> Path:
        return self.legacy_memory / "long_term" / "harness.db"

    @property
    def legacy_handoffs(self) -> Path:
        return self.legacy_state / "handoffs"

    @property
    def legacy_rules(self) -> Path:
        return self.root / "agents" / "AGENTS.md"

    @property
    def legacy_agents(self) -> Path:
        return self.root / "agents"

    @property
    def legacy_workflows(self) -> Path:
        return self.root / ".claude" / "commands"

    @property
    def source_workflows(self) -> Path:
        """Neutral authoring catalog used by a harness source checkout."""

        return self.root / "solomon_harness" / "catalog" / "workflows"

    @property
    def legacy_conventions(self) -> Path:
        return self.root / "docs"

    @property
    def legacy_scripts(self) -> Path:
        return self.root / "scripts"

    @property
    def legacy_python_package(self) -> Path:
        return self.root / "solomon_harness"

    @property
    def legacy_skill_sources(self) -> Path:
        return self.root / "skill-sources.json"

    # -- ordered compatibility candidates ------------------------------
    @property
    def config_candidates(self) -> tuple[Path, ...]:
        return (self.config, self.legacy_config)

    @property
    def rules_candidates(self) -> tuple[Path, ...]:
        return (self.rules, self.legacy_rules)

    @property
    def agents_candidates(self) -> tuple[Path, ...]:
        return (self.agents, self.legacy_agents)

    @property
    def workflows_candidates(self) -> tuple[Path, ...]:
        return (self.workflows, self.source_workflows, self.legacy_workflows)

    @property
    def conventions_candidates(self) -> tuple[Path, ...]:
        return (self.conventions, self.legacy_conventions)

    @property
    def scripts_candidates(self) -> tuple[Path, ...]:
        return (self.scripts, self.legacy_scripts)

    @property
    def python_package_candidates(self) -> tuple[Path, ...]:
        return (self.python_package, self.legacy_python_package)

    @property
    def state_candidates(self) -> tuple[Path, ...]:
        return (self.state, self.legacy_state)

    @property
    def handoff_candidates(self) -> tuple[Path, ...]:
        return (self.handoffs, self.previous_handoffs, self.legacy_handoffs)

    @property
    def skill_sources_candidates(self) -> tuple[Path, ...]:
        return (self.skill_sources, self.legacy_skill_sources)

    # -- read-side compatibility resolvers -----------------------------
    def resolve_config(self) -> Path:
        return _preferred_path(self.config_candidates, directory=False)

    def resolve_rules(self) -> Path:
        return _preferred_path(self.rules_candidates, directory=False)

    def resolve_agents(self) -> Path:
        return _preferred_path(self.agents_candidates, directory=True)

    def resolve_workflows(self) -> Path:
        return _preferred_path(self.workflows_candidates, directory=True)

    def resolve_conventions(self) -> Path:
        return _preferred_path(self.conventions_candidates, directory=True)

    def resolve_scripts(self) -> Path:
        return _preferred_path(self.scripts_candidates, directory=True)

    def resolve_python_package(self) -> Path:
        return _preferred_path(self.python_package_candidates, directory=True)

    def resolve_state(self) -> Path:
        return _preferred_path(self.state_candidates, directory=True)

    def resolve_handoffs(self) -> Path:
        return _preferred_path(self.handoff_candidates, directory=True)

    def resolve_skill_sources(self) -> Path:
        return _preferred_path(self.skill_sources_candidates, directory=False)


def _starting_directory(start: Optional[PathLike]) -> Path:
    candidate = _absolute(start if start is not None else os.getcwd())
    if candidate.is_file():
        return candidate.parent
    return candidate


def _ceiling_directories() -> set[Path]:
    value = os.environ.get("GIT_CEILING_DIRECTORIES", "")
    return {_absolute(item) for item in value.split(os.pathsep) if item}


def _is_workspace_root(candidate: Path) -> bool:
    if (candidate / ".git").exists():
        return True
    if (candidate / ".agents" / "solomon").is_dir():
        return True

    # The legacy payload always carried both trees.  Requiring both avoids
    # treating an unrelated ``agents`` directory or Python package as a root.
    is_installed_core = candidate.name == "solomon" and candidate.parent.name == ".agents"
    if not is_installed_core and (
        (candidate / "agents").is_dir()
        and (candidate / "solomon_harness").is_dir()
    ):
        return True

    # A partially migrated legacy project can retain its config alongside one
    # of the old payload trees.  Config alone is intentionally not a marker:
    # ``.agent`` is not Solomon-specific enough to claim an ancestor.
    if (candidate / ".agent" / "config.json").is_file() and (
        (candidate / "agents").is_dir()
        or (candidate / "solomon_harness").is_dir()
    ):
        return True
    return False


def find_workspace_root(start: Optional[PathLike] = None) -> Path:
    """Find the repository that owns ``start``.

    Discovery recognizes Git worktrees, the canonical installed layout, and
    the legacy two-tree payload.  It respects ``GIT_CEILING_DIRECTORIES`` and
    returns the normalized starting directory when no marker is found, matching
    the CLI's historical standalone behavior. The shared system temp directory
    is always an implicit ceiling: a marker there belongs to another process
    or leftover test state, not this project, and adopting it as the
    workspace root would make later filesystem walks (e.g. codebase indexing)
    scan the whole shared temp directory instead of an isolated one.
    """

    origin = _starting_directory(start)
    ceilings = _ceiling_directories()
    system_tmp = _absolute(tempfile.gettempdir())
    current = origin

    while True:
        if current in ceilings or current == system_tmp or current == current.parent:
            break
        if _is_workspace_root(current):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return origin


__all__ = [
    "HarnessPaths",
    "PathConfinementError",
    "PathLike",
    "confined_path",
    "confined_read_path",
    "find_workspace_root",
]
