"""Install, migrate, upgrade, and remove the repository-local Solomon payload.

The installer owns one host-neutral payload below ``.agents/solomon``.  Files
outside that directory are limited to protocol adapters and project scaffolds.
Every owned file is recorded in a deterministic manifest so upgrades and
uninstalls can distinguish Solomon output from user changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from solomon_harness.adapter_ownership import (
    AdapterOwnershipError,
    TEXT_END as _TEXT_END,
    TEXT_START as _TEXT_START,
    TOML_END as _TOML_END,
    TOML_START as _TOML_START,
    contains_solomon_hook as _contains_solomon_hook,
    managed_adapter_digest as _managed_adapter_digest,
    strategy_for_adapter as _strategy_for_adapter,
)
from solomon_harness.install_lock import (
    install_operation_lock,
    non_materializing_operation_lock,
    operation_lock_path,
)
from solomon_harness.install_transaction import (
    InstallFilePublication,
    UnsafeInstallDirectoryError,
    current_install_root,
    ensure_install_directory,
    ensure_install_parent,
    observe_install_mutations,
    record_install_file_publication,
    record_install_mutation,
)
from solomon_harness.layout import HarnessPaths
from solomon_harness.payload_inventory import (
    PayloadInventoryError,
    claude_metadata_files,
    files_below,
    payload_files,
    workflow_files,
)


SCHEMA_VERSION = 1
LAYOUT_VERSION = 1
HOSTS = ("agy", "claude", "codex")

_DENIED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "memory",
    "node_modules",
    "worktrees",
}
_DENIED_NAMES = {
    "scheduled-loop.lock",
    "secure_vault.enc",
    "settings.local.json",
}
_DENIED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".enc", ".pyc", ".pyo", ".sqlite"}

_CORE_PREFIX = ".agents/solomon/"
_STATE_PREFIX = ".agents/solomon/state/"
_CONFIG_PATH = ".agents/solomon/config/project.json"
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm")
_UV_ENVIRONMENT = "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv"
_UV_PROJECT = "uv run --project .agents/solomon"
_HARNESS_RUN = f"{_UV_ENVIRONMENT} {_UV_PROJECT}"
# Cleanup proofs intentionally cover only the immediately preceding release.
_LEGACY_PROOF_FILES = (
    Path("solomon_harness/legacy_payloads/v0.11.0.tsv"),
    Path("solomon_harness/legacy_payloads/v0.11.0-main.tsv"),
)
_LEGACY_SIGNATURE_PATHS = (
    Path("agents/flutter/skills/navigation.md"),
    Path("scripts/git-hooks/pre-commit"),
    Path("solomon_harness/notify.py"),
)
_LEGACY_ROOT_PAYLOAD_PATHS = {
    Path(".mcp.json"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("AGENTS.md"),
    Path("AGY.md"),
    Path("CLAUDE.md"),
    Path("GEMINI.md"),
    Path("README.md"),
    Path("skill-sources.json"),
    Path(".github/copilot-instructions.md"),
}
_LEGACY_REQUIRED_FOOTPRINT_PATHS = {
    *_LEGACY_SIGNATURE_PATHS,
    Path(".mcp.json"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path("skill-sources.json"),
    Path(".claude/agents/qa.md"),
    Path(".claude/commands/solomon-start.md"),
    Path(".claude/settings.json"),
    Path(".gemini/commands/solomon-start.toml"),
    Path(".gemini/settings.json"),
}


class InstallConflictError(RuntimeError):
    """Raised when installer metadata is invalid or escapes the workspace."""


@dataclass(frozen=True)
class InstallResult:
    """Summary of an install, migration, upgrade, or uninstall operation."""

    changed: bool
    conflicts: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    manifest_path: Path | None = None
    blocking_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class _DesiredFile:
    content: bytes
    mode: int
    owner: str = "core"
    strategy: str = "replace"


@dataclass(frozen=True)
class _PayloadProof:
    sha256: str
    mode: int


@dataclass(frozen=True)
class _FileSnapshot:
    kind: str
    content: bytes | str | None = None
    mode: int = 0
    atime_ns: int = 0
    mtime_ns: int = 0
    device: int = 0
    inode: int = 0


def _capture_file_snapshot(path: Path) -> _FileSnapshot:
    """Capture the state used by rollback compare-and-swap checks."""

    if path.is_symlink():
        return _FileSnapshot("symlink", os.readlink(path))
    if path.is_file():
        info = path.stat()
        return _FileSnapshot(
            "file",
            path.read_bytes(),
            stat.S_IMODE(info.st_mode),
            info.st_atime_ns,
            info.st_mtime_ns,
            info.st_dev,
            info.st_ino,
        )
    if path.is_dir():
        info = path.stat()
        return _FileSnapshot(
            "directory",
            mode=stat.S_IMODE(info.st_mode),
            atime_ns=info.st_atime_ns,
            mtime_ns=info.st_mtime_ns,
            device=info.st_dev,
            inode=info.st_ino,
        )
    return _FileSnapshot("missing")


def _same_file_state(left: _FileSnapshot, right: _FileSnapshot) -> bool:
    """Compare durable state while ignoring read-driven access-time changes."""

    return bool(
        left.kind == right.kind
        and left.content == right.content
        and left.mode == right.mode
        and left.mtime_ns == right.mtime_ns
        and left.device == right.device
        and left.inode == right.inode
    )


class _RollbackSnapshot:
    """Restore transaction writes only while their last observed state matches."""

    def __init__(self, root: Path, targets: Iterable[Path]) -> None:
        self.root = root
        self.files: dict[Path, _FileSnapshot] = {}
        self.expected: dict[Path, _FileSnapshot] = {}
        self.unknown_mutations: set[Path] = set()
        self.directory_paths: set[Path] = {root}
        tracked = {root}
        for path in sorted(set(targets)):
            tracked.add(path)
            parent = path.parent
            while parent != root:
                tracked.add(parent)
                self.directory_paths.add(parent)
                parent = parent.parent
        for path in sorted(tracked):
            snapshot = _capture_file_snapshot(path)
            self.files[path] = snapshot
            if snapshot.kind == "directory":
                self.directory_paths.add(path)

    def checkpoint(self, path: Path) -> None:
        """Remember the exact state immediately after a transaction mutation."""

        target = path if path.is_absolute() else self.root / path
        current = target
        if current not in self.files:
            self.unknown_mutations.add(current)
        while True:
            if current in self.files:
                self.expected[current] = _capture_file_snapshot(current)
            if current == self.root or self.root not in current.parents:
                break
            current = current.parent

    def checkpoint_publication(
        self,
        path: Path,
        publication: InstallFilePublication,
    ) -> None:
        """Record a proven file state without sampling its public path."""

        target = path if path.is_absolute() else self.root / path
        if target not in self.files:
            self.unknown_mutations.add(target)
        else:
            self.expected[target] = _FileSnapshot(
                "file",
                publication.content,
                publication.mode,
                publication.atime_ns,
                publication.mtime_ns,
                publication.device,
                publication.inode,
            )
        current = target.parent
        while True:
            if current in self.files:
                self.expected[current] = _capture_file_snapshot(current)
            if current == self.root or self.root not in current.parents:
                break
            current = current.parent

    @staticmethod
    def _remove_current(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    def rollback(self) -> tuple[str, ...]:
        """Restore matching transaction states and return divergent paths."""

        conflict_paths = set(self.unknown_mutations)
        matching: set[Path] = set()
        for path, expected in self.expected.items():
            if _same_file_state(_capture_file_snapshot(path), expected):
                matching.add(path)
            else:
                conflict_paths.add(path)

        # A tracked target or parent that changed without a checkpoint is not
        # assumed to belong to this transaction. This catches missed observers
        # and external files created in candidate directories.
        for path, original in self.files.items():
            if path in self.expected:
                continue
            if not _same_file_state(_capture_file_snapshot(path), original):
                conflict_paths.add(path)

        def most_specific(paths: set[Path]) -> set[Path]:
            return {
                path
                for path in paths
                if not any(
                    path != candidate and path in candidate.parents
                    for candidate in paths
                )
            }

        conflict_paths = most_specific(conflict_paths)

        divergent_directories = {
            path for path in conflict_paths if path in self.directory_paths
        }

        def blocked_by_directory(path: Path) -> bool:
            return any(
                directory == path or directory in path.parents
                for directory in divergent_directories
            )

        restorable = {
            path for path in matching if not blocked_by_directory(path)
        }

        # Recreate original parents shallow-first so file restoration never uses
        # an implicit mkdir with umask-derived permissions.
        for directory in sorted(
            (
                path
                for path in restorable
                if self.files[path].kind == "directory"
            ),
            key=lambda item: len(item.parts),
        ):
            if not directory.exists():
                snapshot = self.files[directory]
                directory.mkdir(mode=snapshot.mode)
                if os.name != "nt":
                    os.chmod(directory, snapshot.mode)

        for path in sorted(restorable):
            snapshot = self.files[path]
            if snapshot.kind == "directory":
                continue
            if snapshot.kind == "missing":
                self._remove_current(path)
                continue
            if not path.parent.is_dir() or path.parent.is_symlink():
                conflict_paths.add(path.parent)
                continue
            self._remove_current(path)
            if snapshot.kind == "symlink":
                path.symlink_to(str(snapshot.content))
                continue
            path.write_bytes(
                snapshot.content if isinstance(snapshot.content, bytes) else b""
            )
            os.chmod(path, snapshot.mode)
            os.utime(path, ns=(snapshot.atime_ns, snapshot.mtime_ns))

        # Remove only directories whose post-mutation state matched a recorded
        # checkpoint. An unobserved directory is never assumed to be ours.
        for directory in sorted(
            (
                path
                for path in restorable
                if path in self.directory_paths
                and self.files[path].kind == "missing"
            ),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                if not (directory.exists() or directory.is_symlink()):
                    continue
                if not any(
                    conflict == directory or directory in conflict.parents
                    for conflict in conflict_paths
                ):
                    conflict_paths.add(directory)

        # Child restoration changes parent mtimes. Restore original directory
        # metadata only after every file and directory structural operation.
        for directory in sorted(
            (
                path
                for path in restorable
                if self.files[path].kind == "directory" and path.is_dir()
            ),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            snapshot = self.files[directory]
            if os.name != "nt":
                os.chmod(directory, snapshot.mode)
            os.utime(directory, ns=(snapshot.atime_ns, snapshot.mtime_ns))
        conflict_paths = most_specific(conflict_paths)
        return tuple(sorted(_relative(self.root, path) for path in conflict_paths))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise InstallConflictError(f"Path escapes the workspace: {path}") from exc


def _confined_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or relative in {"", "."}:
        raise InstallConflictError(f"Invalid managed path: {relative!r}")
    target = root.joinpath(*candidate.parts)
    resolved_parent = target.parent.resolve()
    try:
        resolved_parent.relative_to(root.resolve())
    except ValueError as exc:
        raise InstallConflictError(f"Managed path escapes the workspace: {relative}") from exc
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise InstallConflictError(f"Managed path traverses a symlink: {relative}")
        cursor = cursor.parent
    return target


def _is_denied(relative: Path) -> bool:
    if any(part in _DENIED_PARTS for part in relative.parts):
        return True
    if relative.name in _DENIED_NAMES:
        return True
    return any(relative.name.endswith(suffix) for suffix in _DENIED_SUFFIXES)


def _read_source(path: Path, source_root: Path) -> tuple[bytes, int]:
    relative = path.relative_to(source_root)
    if _is_denied(relative):
        raise InstallConflictError(f"Denied source file selected for installation: {relative}")
    if path.is_symlink():
        raise InstallConflictError(f"Symlinks are not allowed in the payload: {relative}")
    resolved = path.resolve()
    try:
        resolved.relative_to(source_root.resolve())
    except ValueError as exc:
        raise InstallConflictError(f"Source path escapes the payload root: {relative}") from exc
    return path.read_bytes(), _mode(path)


def _iter_tree(
    source_root: Path,
    relative: Path,
    inventory: Iterable[Path],
) -> Iterable[tuple[Path, Path]]:
    for child in files_below(inventory, relative):
        source = source_root / relative / child
        yield source, child


def _neutral_text(content: bytes) -> bytes:
    """Rewrite source-repository paths in installed instruction markdown."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    replacements = (
        (".claude/commands/", ".agents/solomon/workflows/"),
        ("solomon_harness/catalog/workflows/", ".agents/solomon/workflows/"),
        ("docs/solomon-workflow.md", ".agents/solomon/conventions/solomon-workflow.md"),
        ("docs/release-policy.md", ".agents/solomon/conventions/release-policy.md"),
        ("docs/loop-engineering.md", ".agents/solomon/conventions/loop-engineering.md"),
        ("agents/AGENTS.md", ".agents/solomon/AGENTS.md"),
        (".agents/solomon/handoffs", ".agents/solomon/state/handoffs"),
        (".solomon/handoffs", ".agents/solomon/state/handoffs"),
        (".solomon/", ".agents/solomon/state/"),
        ("Gemini CLI", "AGY"),
        ("Antigravity CLI", "AGY"),
    )
    for old, new in replacements:
        text = text.replace(old, new)

    root_paths = (
        ("scripts/", ".agents/solomon/scripts/"),
        ("solomon_harness/", ".agents/solomon/solomon_harness/"),
        ("agents/", ".agents/solomon/agents/"),
    )
    for old, new in root_paths:
        text = re.sub(rf"(?<![\w./]){re.escape(old)}", new, text)

    direct_cli = re.compile(
        r"(?<!uv run )(?<!project \.agents/solomon )"
        r"\bsolomon-harness(?=\s+(?:broker|claim|dev|loop-policy)\b)"
    )
    text = direct_cli.sub(f"{_HARNESS_RUN} solomon-harness", text)
    text = text.replace("uv run solomon-harness", f"{_HARNESS_RUN} solomon-harness")
    text = text.replace(
        "uv run python -I -m solomon_harness",
        f"{_HARNESS_RUN} python -I -m solomon_harness",
    )
    text = text.replace(
        "uv run python -m solomon_harness",
        f"{_HARNESS_RUN} python -I -m solomon_harness",
    )
    text = text.replace(
        "uv run python -I .agents/solomon/scripts/",
        f"{_HARNESS_RUN} python -I .agents/solomon/scripts/",
    )
    text = text.replace(
        "uv run python .agents/solomon/scripts/",
        f"{_HARNESS_RUN} python -I .agents/solomon/scripts/",
    )
    text = text.replace(
        'uv run python -I -c "import solomon_harness"',
        f'{_HARNESS_RUN} python -I -c "import solomon_harness"',
    )
    text = text.replace(
        'uv run python -c "import solomon_harness"',
        f'{_HARNESS_RUN} python -I -c "import solomon_harness"',
    )
    return text.encode("utf-8")


def _neutral_agent_config(content: bytes) -> bytes:
    """Remove model ownership from canonical specialist configuration."""

    try:
        data = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return content
    if not isinstance(data, dict):
        return content
    data.pop("models", None)
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def _installed_pyproject(source: bytes) -> bytes:
    """Turn the repository pyproject into an installable nested project."""

    text = source.decode("utf-8")
    text = text.replace(
        "[tool.uv]\n# This repository is an application and a template tree, not an installable package.\npackage = false\n\n",
        "",
    )
    if "[build-system]" not in text:
        text += (
            "\n[build-system]\n"
            'requires = ["setuptools>=68"]\n'
            'build-backend = "setuptools.build_meta"\n'
        )
    return text.encode("utf-8")


def _resolve_source_root(source_root: str | Path | None) -> Path:
    if source_root is not None:
        root = Path(source_root).expanduser().resolve()
    else:
        package_root = Path(__file__).resolve().parent
        payload = package_root / "_payload"
        root = payload if (payload / "agents").is_dir() else package_root.parent
    if not (root / "agents").is_dir():
        raise InstallConflictError(f"Harness payload is unavailable at {root}")
    return root


def _add_file(
    desired: dict[str, _DesiredFile],
    target: str,
    content: bytes,
    mode: int,
    *,
    owner: str = "core",
    strategy: str = "replace",
) -> None:
    if target in desired:
        raise InstallConflictError(f"Duplicate install target: {target}")
    desired[target] = _DesiredFile(content, mode, owner, strategy)


def _build_desired(source_root: Path) -> dict[str, _DesiredFile]:
    desired: dict[str, _DesiredFile] = {}
    try:
        inventory = set(payload_files(source_root))
        workflows = workflow_files(source_root)
        claude_metadata = claude_metadata_files(source_root)
    except PayloadInventoryError as exc:
        raise InstallConflictError(str(exc)) from exc

    rules_path = source_root / "agents" / "AGENTS.md"
    rules, rules_mode = _read_source(rules_path, source_root)
    _add_file(desired, f"{_CORE_PREFIX}AGENTS.md", _neutral_text(rules), rules_mode)

    for source, relative in _iter_tree(source_root, Path("agents"), inventory):
        if relative == Path("AGENTS.md"):
            continue
        content, mode = _read_source(source, source_root)
        if relative.parts[-2:] == (".agent", "config.json"):
            content = _neutral_agent_config(content)
        elif source.suffix == ".md":
            content = _neutral_text(content)
        target = Path(_CORE_PREFIX) / "agents" / relative
        _add_file(desired, target.as_posix(), content, mode)

    for workflow_relative in workflows:
        source = source_root / workflow_relative
        content, mode = _read_source(source, source_root)
        _add_file(
            desired,
            f"{_CORE_PREFIX}workflows/{source.name}",
            _neutral_text(content),
            mode,
        )

    for metadata_relative in claude_metadata:
        source = source_root / metadata_relative
        content, mode = _read_source(source, source_root)
        _add_file(
            desired,
            f"{_CORE_PREFIX}host-metadata/claude/commands/{source.name}",
            _neutral_text(content),
            mode,
        )

    conventions = ("solomon-workflow.md", "release-policy.md", "loop-engineering.md")
    for name in conventions:
        source = source_root / "docs" / name
        content, mode = _read_source(source, source_root)
        _add_file(
            desired,
            f"{_CORE_PREFIX}conventions/{name}",
            _neutral_text(content),
            mode,
        )

    for source, relative in _iter_tree(source_root, Path("scripts"), inventory):
        content, mode = _read_source(source, source_root)
        _add_file(desired, (Path(_CORE_PREFIX) / "scripts" / relative).as_posix(), content, mode)

    for source, relative in _iter_tree(source_root, Path("solomon_harness"), inventory):
        if relative.parts[:2] in {
            ("catalog", "workflows"),
            ("host_metadata", "claude"),
        }:
            continue
        content, mode = _read_source(source, source_root)
        _add_file(
            desired,
            (Path(_CORE_PREFIX) / "solomon_harness" / relative).as_posix(),
            content,
            mode,
        )

    pyproject, pyproject_mode = _read_source(source_root / "pyproject.toml", source_root)
    _add_file(
        desired,
        f"{_CORE_PREFIX}pyproject.toml",
        _installed_pyproject(pyproject),
        pyproject_mode,
    )
    for name in ("docker-compose.yml", "uv.lock", "skill-sources.json"):
        source = source_root / name
        if source.is_file():
            content, mode = _read_source(source, source_root)
            _add_file(desired, f"{_CORE_PREFIX}{name}", content, mode)

    _add_file(
        desired,
        f"{_CORE_PREFIX}state/.gitignore",
        b"*\n!.gitignore\n",
        0o644,
        owner="state",
        strategy="create-only",
    )
    _add_file(
        desired,
        _CONFIG_PATH,
        b"{}\n",
        0o600,
        owner="project",
        strategy="create-only",
    )

    scaffold_files = (
        "docs/adrs/0000-adr-template.md",
        "docs/adrs/README.md",
        "docs/specs/0000-spec-template.md",
        "docs/specs/README.md",
    )
    for scaffold_relative in scaffold_files:
        source = source_root / scaffold_relative
        content, mode = _read_source(source, source_root)
        _add_file(
            desired,
            scaffold_relative,
            content,
            mode,
            owner="project",
            strategy="create-only",
        )

    for source, _ in _iter_tree(source_root, Path(".github"), inventory):
        content, mode = _read_source(source, source_root)
        github_relative = source.relative_to(source_root).as_posix()
        _add_file(
            desired,
            github_relative,
            content,
            mode,
            owner="project",
            strategy="create-only",
        )

    return desired


def _atomic_write(
    path: Path,
    content: bytes,
    mode: int,
    *,
    allow_unsafe_existing_parent: bool = False,
) -> bool:
    if path.is_symlink():
        raise InstallConflictError(f"Refusing to replace symlink: {path}")
    transaction_root = current_install_root()
    if transaction_root is not None:
        ensure_install_parent(
            transaction_root,
            path,
            private_root=HarnessPaths(transaction_root).state,
            allow_unsafe_existing=allow_unsafe_existing_parent,
        )
    elif not path.parent.is_dir() or path.parent.is_symlink():
        raise InstallConflictError(
            f"Atomic install write requires an existing safe parent: {path.parent}"
        )
    if path.is_file() and path.read_bytes() == content and _mode(path) == mode:
        return False
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        info = temporary.stat()
        publication = InstallFilePublication(
            content=content,
            mode=stat.S_IMODE(info.st_mode),
            atime_ns=info.st_atime_ns,
            mtime_ns=info.st_mtime_ns,
            device=info.st_dev,
            inode=info.st_ino,
        )
        os.replace(temporary, path)
        record_install_file_publication(path, publication)
    finally:
        temporary_existed = temporary.exists()
        temporary.unlink(missing_ok=True)
        if temporary_existed:
            record_install_mutation(path.parent)
    return True


def _manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        raise InstallConflictError("The install manifest entries must be a list")
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise InstallConflictError("The install manifest contains an invalid entry")
        _validate_manifest_entry(entry)
        relative = entry["path"]
        if relative in result:
            raise InstallConflictError(f"Duplicate managed path in manifest: {relative}")
        result[relative] = entry
    return result


def _adapter_path_allowed(relative: str) -> bool:
    fixed = {
        ".agents/hooks.json",
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".agents/plugins/solomon/plugin.json",
        ".claude/CLAUDE.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".mcp.json",
        "AGENTS.md",
    }
    if relative in fixed:
        return True
    parts = Path(relative).parts
    return bool(
        (
            len(parts) == 4
            and parts[:2] == (".agents", "agents")
            and parts[2]
            and parts[3] == "agent.md"
        )
        or (
            len(parts) == 4
            and parts[:2] == (".agents", "skills")
            and parts[2].startswith("solomon-")
            and parts[3] == "SKILL.md"
        )
        or (len(parts) == 3 and parts[:2] == (".claude", "agents") and parts[2].endswith(".md"))
        or (
            len(parts) == 4
            and parts[:2] == (".claude", "skills")
            and parts[2].startswith("solomon-")
            and parts[3] == "SKILL.md"
        )
        or (len(parts) == 3 and parts[:2] == (".codex", "agents") and parts[2].endswith(".toml"))
    )


def _project_path_allowed(relative: str) -> bool:
    if relative == _CONFIG_PATH:
        return True
    if relative in {
        ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/adrs/0000-adr-template.md",
        "docs/adrs/README.md",
        "docs/specs/0000-spec-template.md",
        "docs/specs/README.md",
    }:
        return True
    parts = Path(relative).parts
    return len(parts) == 3 and parts[:2] == (".github", "ISSUE_TEMPLATE")


def _desired_conflict_is_blocking(relative: str) -> bool:
    """Treat every conflict inside the canonical harness root as blocking."""

    return relative.startswith(_CORE_PREFIX)


def _validate_manifest_entry(entry: dict[str, Any]) -> None:
    relative = entry.get("path")
    owner = entry.get("owner")
    strategy = entry.get("strategy")
    digest = entry.get("sha256")
    mode = entry.get("mode")
    if owner not in {"adapter", "core", "project"}:
        raise InstallConflictError(f"Invalid manifest owner for {relative!r}")
    if strategy not in {"replace", "create-only", "json-merge", "toml-merge", "marker-merge"}:
        raise InstallConflictError(f"Invalid manifest strategy for {relative!r}")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise InstallConflictError(f"Invalid manifest digest for {relative!r}")
    if not isinstance(mode, str) or re.fullmatch(r"0[0-7]{3}", mode) is None:
        raise InstallConflictError(f"Invalid manifest mode for {relative!r}")

    allowed = False
    if owner == "core" and isinstance(relative, str):
        allowed = relative.startswith(_CORE_PREFIX) and relative not in {
            _CONFIG_PATH,
            f"{_CORE_PREFIX}manifest.json",
        }
    elif owner == "project" and isinstance(relative, str):
        allowed = _project_path_allowed(relative)
    elif owner == "adapter" and isinstance(relative, str):
        allowed = _adapter_path_allowed(relative)
    if not allowed:
        raise InstallConflictError(f"Manifest path is outside its owner namespace: {relative!r}")

    if owner == "adapter" and strategy != _strategy_for_adapter(str(relative)):
        raise InstallConflictError(f"Manifest adapter strategy does not match {relative!r}")
    if owner == "core" and strategy not in {"replace", "create-only"}:
        raise InstallConflictError(f"Invalid core strategy for {relative!r}")
    if owner == "project" and strategy != "create-only":
        raise InstallConflictError(f"Invalid project strategy for {relative!r}")
    if "created" in entry and not isinstance(entry["created"], bool):
        raise InstallConflictError(f"Invalid creation marker for {relative!r}")
    base_digest = entry.get("base_sha256")
    if base_digest is not None and (
        not isinstance(base_digest, str) or re.fullmatch(r"[0-9a-f]{64}", base_digest) is None
    ):
        raise InstallConflictError(f"Invalid base digest for {relative!r}")
    managed_digest = entry.get("managed_sha256")
    if managed_digest is not None and (
        owner != "adapter"
        or strategy not in {"json-merge", "toml-merge", "marker-merge"}
        or not isinstance(managed_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", managed_digest) is None
    ):
        raise InstallConflictError(f"Invalid managed digest for {relative!r}")


def load_manifest(root: str | Path) -> dict[str, Any]:
    """Load and validate a workspace manifest.

    Missing manifests are represented by an empty manifest for upgrade callers.
    Present manifests fail closed when any path is absolute, traverses upward, or
    resolves through a parent symlink outside the workspace.
    """

    paths = HarnessPaths(root)
    _confined_path(
        paths.root,
        paths.manifest.relative_to(paths.root).as_posix(),
    )
    if not paths.manifest.is_file():
        return {}
    try:
        manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallConflictError(f"Cannot read install manifest: {paths.manifest}") from exc
    if not isinstance(manifest, dict):
        raise InstallConflictError("The install manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise InstallConflictError("Unsupported install manifest schema")
    for relative in _manifest_entries(manifest):
        _confined_path(paths.root, relative)
    return manifest


def immutable_managed_paths(root: str | Path) -> tuple[str, ...]:
    """Return installed paths an autonomous host hook must not modify.

    The manifest itself and entries owned by the harness core or a native host
    adapter form the runtime trust boundary. Project-owned scaffolds are
    intentionally excluded so normal product development remains possible.
    A malformed present manifest raises :class:`InstallConflictError`; callers
    enforcing policy must fail closed rather than silently dropping protection.
    """

    paths = HarnessPaths(root)
    mandatory = (
        # Canonical immutable runtime and catalogs. These paths remain trusted
        # while a fresh install is still assembling its manifest.
        paths.rules,
        paths.agents,
        paths.workflows,
        paths.conventions,
        paths.solomon / "host-metadata",
        paths.scripts,
        paths.python_package,
        paths.pyproject,
        paths.solomon / "docker-compose.yml",
        paths.lockfile,
        paths.skill_sources,
        paths.config,
        paths.manifest,
        paths.state / ".gitignore",
        paths.state / "install.lock",
        paths.state / "venv",
        # Native discovery bridges can disable the guard that protects the
        # canonical core, so they are trust roots even before a manifest exists.
        paths.root_instructions,
        paths.agents_root / "agents",
        paths.shared_skills,
        paths.agy_hooks,
        paths.agy_plugins,
        paths.claude_instructions,
        paths.claude_agents,
        paths.claude_skills,
        paths.claude_settings,
        paths.claude_mcp,
        paths.codex_agents,
        paths.codex_config,
        paths.codex_hooks,
        paths.legacy_config,
    )
    protected = {
        target.relative_to(paths.root).as_posix()
        for target in mandatory
    }
    manifest = load_manifest(paths.root)
    if not manifest:
        return tuple(sorted(protected))
    protected.update(
        relative
        for relative, entry in _manifest_entries(manifest).items()
        if entry.get("owner") in {"adapter", "core"}
    )
    return tuple(sorted(protected))


def _remove_empty_parents(path: Path, root: Path, protected: set[Path]) -> None:
    parent = path.parent
    while parent != root and parent not in protected:
        try:
            parent.rmdir()
        except OSError:
            return
        record_install_mutation(parent)
        parent = parent.parent


def _ensure_private_directory(path: Path) -> bool:
    """Create one state directory and remove group/other access on POSIX."""

    existed = path.is_dir()
    previous_mode = _mode(path) if existed else None
    transaction_root = current_install_root()
    if transaction_root is None:
        raise InstallConflictError(
            f"Private state directory requires an install transaction: {path}"
        )
    try:
        ensure_install_directory(
            transaction_root,
            path,
            private_root=HarnessPaths(transaction_root).state,
        )
    except UnsafeInstallDirectoryError as exc:
        raise InstallConflictError(str(exc)) from exc
    changed = not existed or (
        os.name != "nt" and previous_mode != _PRIVATE_DIRECTORY_MODE
    )
    return changed


def _ensure_private_state_directories(state: Path, target: Path) -> bool:
    """Privatize every directory from the canonical state root to ``target``."""

    try:
        relative = target.relative_to(state)
    except ValueError as exc:
        raise InstallConflictError(f"State path escapes the canonical root: {target}") from exc
    changed = _ensure_private_directory(state)
    current = state
    for part in relative.parts:
        current /= part
        changed |= _ensure_private_directory(current)
    return changed


def _harden_existing_state_directories(state: Path) -> bool:
    """Apply the private-directory contract to an existing state tree."""

    if not state.exists():
        return False
    if state.is_symlink() or not state.is_dir():
        raise InstallConflictError(f"Canonical state path is not a directory: {state}")
    changed = _ensure_private_directory(state)
    for directory in sorted(path for path in state.rglob("*") if path.is_dir()):
        if directory.is_symlink():
            raise InstallConflictError(f"Canonical state traverses a symlink: {directory}")
        changed |= _ensure_private_directory(directory)
    return changed


def _sqlite_files(database: Path) -> tuple[Path, ...]:
    return (database, *(Path(f"{database}{suffix}") for suffix in _SQLITE_SIDECAR_SUFFIXES))


def _validated_sqlite_digest(connection: sqlite3.Connection, label: str) -> str:
    """Hash a deterministic logical dump after SQLite's full integrity check."""

    rows = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
    if rows != ("ok",):
        detail = "; ".join(rows) if rows else "no integrity result"
        raise InstallConflictError(f"{label} failed integrity_check: {detail}")
    digest = hashlib.sha256()
    for statement in connection.iterdump():
        encoded = statement.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _read_sqlite_digest(database: Path, label: str) -> str:
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            return _validated_sqlite_digest(connection, label)
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise InstallConflictError(f"Cannot validate {label} at {database}: {exc}") from exc


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _backup_legacy_sqlite(source: Path, destination: Path) -> None:
    """Create and verify a consolidated SQLite backup, including committed WAL."""

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.migration.",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    source_connection: sqlite3.Connection | None = None
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(
            f"{source.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        source_connection.execute("BEGIN")
        source_digest = _validated_sqlite_digest(
            source_connection,
            "legacy SQLite database",
        )
        target_connection = sqlite3.connect(temporary)
        source_connection.backup(target_connection)
        target_connection.commit()
        target_connection.execute("PRAGMA journal_mode=DELETE")
        target_digest = _validated_sqlite_digest(
            target_connection,
            "SQLite migration backup",
        )
        if target_digest != source_digest:
            raise InstallConflictError(
                "SQLite migration backup does not match the legacy database"
            )
        target_connection.close()
        target_connection = None
        source_connection.rollback()
        source_connection.close()
        source_connection = None
        os.chmod(temporary, _PRIVATE_FILE_MODE)
        _fsync_file(temporary)
        os.replace(temporary, destination)
        record_install_mutation(destination)
        _fsync_directory(destination.parent)
        if (
            _read_sqlite_digest(destination, "canonical SQLite database")
            != source_digest
        ):
            raise InstallConflictError(
                "Canonical SQLite database does not match the verified migration backup"
            )
    except (OSError, sqlite3.Error) as exc:
        raise InstallConflictError(f"Cannot migrate legacy SQLite database: {exc}") from exc
    finally:
        if target_connection is not None:
            target_connection.close()
        if source_connection is not None:
            source_connection.close()
        temporary_existed = temporary.exists()
        temporary.unlink(missing_ok=True)
        if temporary_existed:
            record_install_mutation(destination.parent)


def _remove_legacy_sqlite(database: Path) -> None:
    for path in _sqlite_files(database):
        if path.exists() or path.is_symlink():
            path.unlink(missing_ok=True)
            record_install_mutation(path)


def _migrate_legacy_sqlite(paths: HarnessPaths) -> tuple[bool, tuple[str, ...]]:
    """Move the pre-layout fallback database without losing committed WAL pages."""

    source = paths.legacy_sqlite_database
    destination = paths.sqlite_database
    present_sidecars = tuple(path for path in _sqlite_files(source)[1:] if path.exists())
    if not source.exists():
        return False, tuple(_relative(paths.root, path) for path in present_sidecars)
    if source.is_symlink() or not source.is_file():
        raise InstallConflictError(f"Legacy SQLite path is not a regular file: {source}")

    source_digest = _read_sqlite_digest(source, "legacy SQLite database")
    changed = _ensure_private_state_directories(paths.state, destination.parent)
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            return changed, (_relative(paths.root, source),)
        try:
            destination_digest = _read_sqlite_digest(
                destination,
                "canonical SQLite database",
            )
        except InstallConflictError:
            return changed, (_relative(paths.root, source),)
        if destination_digest != source_digest:
            return changed, (_relative(paths.root, source),)
        if os.name != "nt":
            for database_file in _sqlite_files(destination):
                if database_file.exists() and _mode(database_file) != _PRIVATE_FILE_MODE:
                    os.chmod(database_file, _PRIVATE_FILE_MODE)
                    record_install_mutation(database_file)
                    changed = True
    else:
        _backup_legacy_sqlite(source, destination)
        changed = True

    _remove_legacy_sqlite(source)
    return True, ()


def _validate_legacy_paths(paths: HarnessPaths) -> None:
    """Reject legacy migration sources that traverse any symlink."""

    if paths.legacy_config.exists() or paths.legacy_config.is_symlink():
        _confined_path(paths.root, paths.legacy_config.relative_to(paths.root).as_posix())
    if paths.legacy_state.exists() or paths.legacy_state.is_symlink():
        _confined_path(
            paths.root,
            paths.legacy_state.relative_to(paths.root).as_posix(),
        )
        if paths.legacy_state.is_dir():
            for source in paths.legacy_state.rglob("*"):
                _confined_path(paths.root, source.relative_to(paths.root).as_posix())
    for source in _sqlite_files(paths.legacy_sqlite_database):
        if source.exists() or source.is_symlink():
            _confined_path(paths.root, source.relative_to(paths.root).as_posix())


def _handoff_migration_pairs(paths: HarnessPaths) -> tuple[tuple[Path, Path], ...]:
    """Preflight the pre-state canonical handoff tree and every destination."""

    previous = paths.previous_handoffs
    if not (previous.exists() or previous.is_symlink()):
        return ()
    _confined_path(paths.root, previous.relative_to(paths.root).as_posix())
    if not previous.is_dir():
        raise InstallConflictError(
            f"Previous handoff path is not a directory: {_relative(paths.root, previous)}"
        )

    pairs: list[tuple[Path, Path]] = []
    for source in sorted(previous.rglob("*")):
        _confined_path(paths.root, source.relative_to(paths.root).as_posix())
        if source.is_dir():
            continue
        if not source.is_file():
            raise InstallConflictError(
                f"Previous handoff entry is not a file: {_relative(paths.root, source)}"
            )
        destination = paths.handoffs / source.relative_to(previous)
        destination = _confined_path(
            paths.root,
            destination.relative_to(paths.root).as_posix(),
        )
        pairs.append((source, destination))
    return tuple(pairs)


def _same_payload_file(target: Path, source: Path) -> bool:
    return bool(
        target.is_file()
        and not target.is_symlink()
        and target.read_bytes() == source.read_bytes()
        and _mode(target) == _mode(source)
    )


def _legacy_payload_sources(source_root: Path) -> dict[Path, Path]:
    """Map recognized legacy project paths to their allowlisted sources."""

    try:
        inventory = payload_files(source_root)
        metadata = claude_metadata_files(source_root)
    except PayloadInventoryError as exc:
        raise InstallConflictError(str(exc)) from exc

    result = {
        relative: source_root / relative
        for relative in inventory
        if relative.parts[0] in {"agents", "scripts", "solomon_harness"}
    }
    for relative in metadata:
        result[Path(".claude/commands") / relative.name] = source_root / relative
    return result


def _legacy_proof_path_allowed(relative: Path) -> bool:
    if not relative.parts:
        return False
    if relative.parts[0] in {"agents", "docs", "scripts", "solomon_harness"}:
        return True
    if relative.parts[0] in {".claude", ".gemini"}:
        return True
    return relative in _LEGACY_ROOT_PAYLOAD_PATHS


def _load_legacy_proof_catalog(
    source_root: Path,
    catalog_relative: Path,
) -> tuple[str, dict[Path, _PayloadProof]]:
    catalog = source_root / catalog_relative
    try:
        content, _ = _read_source(catalog, source_root)
        lines = content.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallConflictError(
            f"Cannot read legacy payload proof catalog: {catalog_relative}"
        ) from exc
    if not lines:
        raise InstallConflictError(f"Empty legacy payload proof catalog: {catalog_relative}")
    header = lines[0].split("\t")
    if len(header) != 2 or header[0] != "solomon-harness-legacy-payload-v1":
        raise InstallConflictError(f"Invalid legacy payload proof catalog: {catalog_relative}")

    proofs: dict[Path, _PayloadProof] = {}
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != 3:
            raise InstallConflictError(f"Invalid legacy payload proof entry in {catalog_relative}")
        mode_text, digest, relative_text = fields
        relative = Path(relative_text)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != relative_text
            or not _legacy_proof_path_allowed(relative)
            or re.fullmatch(r"0[0-7]{3}", mode_text) is None
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or relative in proofs
        ):
            raise InstallConflictError(
                f"Unsafe legacy payload proof entry in {catalog_relative}: {relative_text!r}"
            )
        proofs[relative] = _PayloadProof(digest, int(mode_text, 8))
    if not _LEGACY_REQUIRED_FOOTPRINT_PATHS <= set(proofs):
        raise InstallConflictError(
            f"Legacy payload proof catalog lacks its required footprint: {catalog_relative}"
        )
    return header[1], proofs


def _legacy_payload_proof_sets(
    source_root: Path,
) -> tuple[tuple[str, dict[Path, _PayloadProof]], ...]:
    sources = _legacy_payload_sources(source_root)
    current = {
        relative: _PayloadProof(_sha256(source.read_bytes()), _mode(source))
        for relative, source in sources.items()
    }
    result: list[tuple[str, dict[Path, _PayloadProof]]] = [("current", current)]
    for catalog_relative in _LEGACY_PROOF_FILES:
        result.append(_load_legacy_proof_catalog(source_root, catalog_relative))
    return tuple(result)


def _matches_payload_proof(
    root: Path,
    relative: Path,
    proof: _PayloadProof,
) -> bool:
    try:
        target = _confined_path(root, relative.as_posix())
    except InstallConflictError:
        return False
    return bool(
        target.is_file()
        and not target.is_symlink()
        and _mode(target) == proof.mode
        and _sha256(target.read_bytes()) == proof.sha256
    )


def _recognized_legacy_payload_proofs(
    root: Path,
    source_root: Path,
) -> dict[Path, set[_PayloadProof]]:
    matching: list[dict[Path, _PayloadProof]] = []
    for _, proofs in _legacy_payload_proof_sets(source_root):
        signature_matches = sum(
            1
            for relative in _LEGACY_SIGNATURE_PATHS
            if (proof := proofs.get(relative)) is not None
            and _matches_payload_proof(root, relative, proof)
        )
        if signature_matches >= 2:
            matching.append(proofs)

    recognized: dict[Path, set[_PayloadProof]] = {}
    for proofs in matching:
        for relative, proof in proofs.items():
            recognized.setdefault(relative, set()).add(proof)
    return recognized


def _unowned_gemini_paths(root: Path) -> set[str]:
    gemini = root / ".gemini"
    if gemini.is_symlink():
        return {".gemini"}
    if not gemini.is_dir():
        return set()
    paths = {
        target.relative_to(root).as_posix()
        for target in gemini.rglob("*")
        if target.is_file() or target.is_symlink()
    }
    return paths or {".gemini"}


_LEGACY_MCP_SERVER = {
    "command": "uv",
    "args": ["run", "python", "-m", "solomon_harness.mcp_server"],
}
_LEGACY_CLAUDE_HOOKS = {
    "SessionStart": {
        "hooks": [
            {
                "type": "command",
                "command": (
                    "uv run python -m solomon_harness.cli memory-up "
                    "2>/dev/null || true"
                ),
            },
            {
                "type": "command",
                "command": (
                    "uv run python -m solomon_harness.cli run "
                    "2>/dev/null || true"
                ),
            },
        ]
    },
    "PreToolUse": {
        "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
            {
                "type": "command",
                "command": "uv run python -m solomon_harness.cli loop-guard",
            }
        ],
    },
}


def _matches_any_legacy_proof(
    root: Path,
    relative: Path,
    proofs: dict[Path, set[_PayloadProof]],
) -> bool:
    return any(
        _matches_payload_proof(root, relative, proof)
        for proof in proofs.get(relative, set())
    )


def _remove_legacy_shared_adapter_nodes(
    root: Path,
    proofs: dict[Path, set[_PayloadProof]],
) -> set[Path]:
    """Remove exact v0.11 nodes from modified shared JSON adapters."""

    migrated: set[Path] = set()
    for relative in (Path(".mcp.json"), Path(".claude/settings.json")):
        path = _confined_path(root, relative.as_posix())
        if (
            not path.is_file()
            or path.is_symlink()
            or _matches_any_legacy_proof(root, relative, proofs)
        ):
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        changed = False
        if relative == Path(".mcp.json"):
            servers = document.get("mcpServers")
            if (
                isinstance(servers, dict)
                and servers.get("solomon-memory") == _LEGACY_MCP_SERVER
            ):
                servers.pop("solomon-memory")
                if not servers:
                    document.pop("mcpServers", None)
                changed = True
        else:
            hooks = document.get("hooks")
            if isinstance(hooks, dict):
                for event, legacy_node in _LEGACY_CLAUDE_HOOKS.items():
                    values = hooks.get(event)
                    if not isinstance(values, list):
                        continue
                    retained = [value for value in values if value != legacy_node]
                    if retained != values:
                        changed = True
                        if retained:
                            hooks[event] = retained
                        else:
                            hooks.pop(event, None)
                if not hooks:
                    document.pop("hooks", None)
        if not changed:
            continue
        _atomic_write(
            path,
            (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
            _mode(path),
        )
        migrated.add(relative)
    return migrated


def _cleanup_legacy_payload(root: Path, source_root: Path) -> tuple[bool, tuple[str, ...]]:
    """Remove only byte-and-mode-identical files from the former root layout."""

    if root.resolve() == source_root.resolve():
        return False, ()
    conflicts: set[str] = set()
    proofs = _recognized_legacy_payload_proofs(root, source_root)
    if not proofs:
        conflicts.update(_unowned_gemini_paths(root))
        for relative in _LEGACY_SIGNATURE_PATHS:
            if (root / relative).exists():
                conflicts.add(relative.as_posix())
        return False, tuple(sorted(conflicts))

    semantically_migrated = _remove_legacy_shared_adapter_nodes(root, proofs)
    changed = bool(semantically_migrated)
    cleanup_roots = (
        root / "agents",
        root / "scripts",
        root / "solomon_harness",
        root / ".claude",
        root / ".gemini",
    )
    for cleanup_root in cleanup_roots:
        if cleanup_root.is_symlink():
            conflicts.add(cleanup_root.relative_to(root).as_posix())
            continue
        if not cleanup_root.is_dir():
            continue
        for target in sorted(cleanup_root.rglob("*")):
            if target.is_dir() and not target.is_symlink():
                continue
            relative = target.relative_to(root)
            if relative in semantically_migrated:
                continue
            if target.is_symlink() or not _matches_any_legacy_proof(
                root,
                relative,
                proofs,
            ):
                conflicts.add(relative.as_posix())
                continue
            target.unlink()
            record_install_mutation(target)
            changed = True
        for directory in sorted(
            (path for path in cleanup_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
            else:
                record_install_mutation(directory)
        try:
            cleanup_root.rmdir()
        except OSError:
            pass
        else:
            record_install_mutation(cleanup_root)

    scanned_prefixes = {"agents", "scripts", "solomon_harness", ".claude", ".gemini"}
    protected = {root, root / "docs", root / ".github"}
    for relative in sorted(proofs):
        if relative.parts[0] in scanned_prefixes or relative in semantically_migrated:
            continue
        target = _confined_path(root, relative.as_posix())
        if not (target.exists() or target.is_symlink()):
            continue
        if target.is_symlink() or not _matches_any_legacy_proof(root, relative, proofs):
            conflicts.add(relative.as_posix())
            continue
        target.unlink()
        record_install_mutation(target)
        _remove_empty_parents(target, root, protected)
        changed = True

    return changed, tuple(sorted(conflicts))


def _migrate_legacy(
    root: Path,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    paths = HarnessPaths(root)
    _validate_legacy_paths(paths)
    handoff_pairs = _handoff_migration_pairs(paths)
    changed = False
    conflicts: list[str] = []

    for source, target in handoff_pairs:
        if not target.exists():
            changed |= _atomic_write(target, source.read_bytes(), _mode(source))
            source.unlink()
            record_install_mutation(source)
            changed = True
        elif _same_payload_file(target, source):
            source.unlink()
            record_install_mutation(source)
            changed = True
        else:
            conflicts.append(_relative(root, source))

    if paths.legacy_config.is_file():
        content = paths.legacy_config.read_bytes()
        if not paths.config.exists():
            changed |= _atomic_write(paths.config, content, _mode(paths.legacy_config))
            paths.legacy_config.unlink()
            record_install_mutation(paths.legacy_config)
            changed = True
        elif paths.config.read_bytes() == content:
            paths.legacy_config.unlink()
            record_install_mutation(paths.legacy_config)
            changed = True
        else:
            conflicts.append(_relative(root, paths.legacy_config))

    if paths.legacy_state.is_dir():
        for source in sorted(paths.legacy_state.rglob("*")):
            if source.is_symlink():
                conflicts.append(_relative(root, source))
                continue
            if not source.is_file():
                continue
            relative = source.relative_to(paths.legacy_state)
            target = _confined_path(
                root,
                (paths.state / relative).relative_to(root).as_posix(),
            )
            changed |= _ensure_private_state_directories(paths.state, target.parent)
            target_mode = (
                _PRIVATE_FILE_MODE
                if relative.parts and relative.parts[0] == "memory-mirror"
                else _mode(source)
            )
            if not target.exists():
                changed |= _atomic_write(target, source.read_bytes(), target_mode)
                source.unlink()
                record_install_mutation(source)
                changed = True
            elif target.is_file() and target.read_bytes() == source.read_bytes():
                if os.name != "nt" and _mode(target) != target_mode:
                    os.chmod(target, target_mode)
                    record_install_mutation(target)
                source.unlink()
                record_install_mutation(source)
                changed = True
            else:
                conflicts.append(_relative(root, source))

    sqlite_changed, sqlite_conflicts = _migrate_legacy_sqlite(paths)
    changed |= sqlite_changed
    conflicts.extend(sqlite_conflicts)

    for legacy in (
        paths.legacy_config.parent,
        paths.legacy_state,
        paths.legacy_memory,
        paths.previous_handoffs,
    ):
        if not legacy.exists():
            continue
        for directory in sorted(
            (path for path in legacy.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
            else:
                record_install_mutation(directory)
        try:
            legacy.rmdir()
            changed = True
        except OSError:
            pass
        else:
            record_install_mutation(legacy)

    return (
        changed,
        tuple(sorted(set(conflicts))),
        tuple(sorted(set(sqlite_conflicts))),
    )


def _entry(relative: str, path: Path, owner: str, strategy: str) -> dict[str, Any]:
    return {
        "path": relative,
        "owner": owner,
        "strategy": strategy,
        "sha256": _sha256(path.read_bytes()),
        "mode": f"{_mode(path):04o}",
    }


def _owned_entry_is_unchanged(path: Path, entry: dict[str, Any]) -> bool:
    """Require both content and permission mode to match recorded ownership."""

    try:
        expected_mode = int(str(entry.get("mode", "")), 8)
    except ValueError:
        return False
    return bool(
        path.is_file()
        and not path.is_symlink()
        and _sha256(path.read_bytes()) == entry.get("sha256")
        and _mode(path) == expected_mode
    )


def _compiled_adapter_entry(
    relative: str,
    target: Path,
    previous_entries: dict[str, dict[str, Any]],
    snapshot: _RollbackSnapshot,
) -> dict[str, Any]:
    """Build one adapter manifest entry without losing its creation proof."""

    adapter_entry = _entry(
        relative,
        target,
        "adapter",
        _strategy_for_adapter(relative),
    )
    if adapter_entry["strategy"] in {
        "json-merge",
        "marker-merge",
        "toml-merge",
    }:
        adapter_entry["managed_sha256"] = _managed_adapter_digest(
            target,
            relative,
        )
    previous_adapter = previous_entries.get(relative, {})
    if "created" in previous_adapter:
        adapter_entry["created"] = bool(previous_adapter["created"])
        if "base_sha256" in previous_adapter:
            adapter_entry["base_sha256"] = previous_adapter["base_sha256"]
        return adapter_entry

    original = snapshot.files.get(target, _FileSnapshot("missing"))
    adapter_entry["created"] = original.kind == "missing"
    if original.kind == "file" and isinstance(original.content, bytes):
        adapter_entry["base_sha256"] = _sha256(original.content)
    return adapter_entry


def _transaction_targets(
    workspace: Path,
    source: Path,
    desired: dict[str, _DesiredFile],
    previous_entries: dict[str, dict[str, Any]],
) -> set[Path]:
    """Enumerate every path this install can write, merge, move, or delete."""

    paths = HarnessPaths(workspace)
    _validate_legacy_paths(paths)
    relative_targets = set(desired) | set(previous_entries)
    relative_targets.update(
        {
            ".agents/hooks.json",
            ".agents/plugins/solomon/mcp_config.json",
            ".agents/plugins/solomon/plugin.json",
            ".claude/CLAUDE.md",
            ".claude/settings.json",
            ".codex/config.toml",
            ".codex/hooks.json",
            ".mcp.json",
            "AGENTS.md",
        }
    )

    specialist_names: set[str] = set()
    for agents_root in (source / "agents", paths.agents):
        if not agents_root.is_dir():
            continue
        for directory in agents_root.iterdir():
            name = directory.name
            if (directory / "agents" / f"{name}.md").is_file():
                specialist_names.add(name)
    for name in sorted(specialist_names):
        relative_targets.update(
            {
                f".agents/agents/{name}/agent.md",
                f".claude/agents/{name}.md",
                f".codex/agents/{name}.toml",
            }
        )
    workflow_names: set[str] = set()
    workflow_prefix = f"{_CORE_PREFIX}workflows/solomon-"
    for relative in desired:
        if not relative.startswith(workflow_prefix) or not relative.endswith(".md"):
            continue
        workflow_names.add(relative.removeprefix(workflow_prefix).removesuffix(".md"))
    if paths.workflows.is_dir():
        for workflow in paths.workflows.glob("*.md"):
            name = workflow.stem.removeprefix("solomon-")
            if name:
                workflow_names.add(name)
    for name in sorted(workflow_names):
        relative_targets.update(
            {
                f".agents/skills/solomon-{name}/SKILL.md",
                f".claude/skills/solomon-{name}/SKILL.md",
            }
        )

    targets = {_confined_path(workspace, relative) for relative in relative_targets}
    targets.add(operation_lock_path(workspace))
    targets.add(paths.manifest)
    targets.add(paths.legacy_config)
    for previous_handoff, destination in _handoff_migration_pairs(paths):
        targets.add(previous_handoff)
        targets.add(destination)
    if workspace.resolve() != source.resolve():
        legacy_proofs = _recognized_legacy_payload_proofs(workspace, source)
        for legacy_relative, candidates in legacy_proofs.items():
            if any(
                _matches_payload_proof(workspace, legacy_relative, proof) for proof in candidates
            ):
                targets.add(workspace / legacy_relative)
    if paths.legacy_state.is_dir():
        for legacy_file in paths.legacy_state.rglob("*"):
            if not legacy_file.is_file():
                continue
            targets.add(legacy_file)
            destination = paths.state / legacy_file.relative_to(paths.legacy_state)
            targets.add(
                _confined_path(
                    workspace,
                    destination.relative_to(workspace).as_posix(),
                )
            )
    legacy_sqlite_files = _sqlite_files(paths.legacy_sqlite_database)
    if any(path.exists() or path.is_symlink() for path in legacy_sqlite_files):
        targets.update(legacy_sqlite_files)
        targets.update(_sqlite_files(paths.sqlite_database))
    return targets


def _harness_version(source_root: Path) -> str:
    try:
        with (source_root / "pyproject.toml").open("rb") as stream:
            return str(tomllib.load(stream).get("project", {}).get("version", "unknown"))
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"


def install_project(
    root: str | Path,
    *,
    source_root: str | Path | None = None,
) -> InstallResult:
    """Install or upgrade the harness in ``root`` without overwriting user edits.

    Preconditions:
        ``root`` is a writable consumer workspace and ``source_root`` resolves to
        a valid allowlisted Solomon payload.
    Postconditions:
        Canonical content and verified mutable state live below
        ``.agents/solomon``; the manifest describes every managed immutable file.
    Invariants:
        Project-owned files, modified adapters, tenant configuration, and memory
        state are never overwritten without an ownership or parity proof.
    Idempotency:
        Repeating the operation with unchanged source and workspace state changes
        no managed bytes, modes, or modification times.
    Errors:
        Raises :class:`InstallConflictError` for unsafe paths, invalid metadata,
        or unverifiable state, and rolls back other failures before re-raising.
    """

    workspace = Path(root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with non_materializing_operation_lock(workspace):
        source = _resolve_source_root(source_root)
        paths = HarnessPaths(workspace)
        previous = load_manifest(workspace)
        previous_entries = _manifest_entries(previous) if previous else {}
        desired = _build_desired(source)
        snapshot = _RollbackSnapshot(
            workspace,
            _transaction_targets(workspace, source, desired, previous_entries),
        )
        try:
            with observe_install_mutations(
                snapshot.checkpoint,
                publication_observer=snapshot.checkpoint_publication,
                root=workspace,
            ):
                with install_operation_lock(workspace):
                    return _apply_install(
                        workspace,
                        source,
                        paths,
                        previous_entries,
                        desired,
                        snapshot,
                    )
        except BaseException as exc:
            rollback_conflicts = snapshot.rollback()
            if rollback_conflicts:
                detail = ", ".join(rollback_conflicts)
                raise InstallConflictError(
                    "Rollback preserved paths changed outside the install "
                    f"transaction: {detail}"
                ) from exc
            raise


def _apply_install(
    workspace: Path,
    source: Path,
    paths: HarnessPaths,
    previous_entries: dict[str, dict[str, Any]],
    desired: dict[str, _DesiredFile],
    snapshot: _RollbackSnapshot,
) -> InstallResult:
    changed, migration_conflicts, migration_blocking = _migrate_legacy(workspace)
    conflicts = set(migration_conflicts)
    blocking_conflicts = set(migration_blocking)
    entries: dict[str, dict[str, Any]] = {}

    for relative, specification in sorted(desired.items()):
        target = _confined_path(workspace, relative)
        project_parent = bool(
            specification.owner == "project"
            and relative != _CONFIG_PATH
            and not relative.startswith(_STATE_PREFIX)
        )
        ensure_install_parent(
            workspace,
            target,
            private_root=paths.state,
            allow_unsafe_existing=project_parent,
        )
        old = previous_entries.get(relative)
        desired_hash = _sha256(specification.content)

        if specification.strategy == "create-only" and target.exists():
            if target.is_symlink() or not target.is_file():
                conflicts.add(relative)
                if _desired_conflict_is_blocking(relative):
                    blocking_conflicts.add(relative)
                continue
            if old and (
                target.read_bytes() == specification.content
                and not relative.startswith(_STATE_PREFIX)
                and relative != _CONFIG_PATH
            ):
                entries[relative] = _entry(
                    relative, target, specification.owner, specification.strategy
                )
            elif old and relative != _CONFIG_PATH and not relative.startswith(_STATE_PREFIX):
                entries[relative] = dict(old)
            continue

        if target.exists() and (target.is_symlink() or not target.is_file()):
            conflicts.add(relative)
            if _desired_conflict_is_blocking(relative):
                blocking_conflicts.add(relative)
            if old:
                entries[relative] = dict(old)
            continue

        if target.is_file():
            matches_desired = (
                _sha256(target.read_bytes()) == desired_hash and _mode(target) == specification.mode
            )
            if not matches_desired and (old is None or not _owned_entry_is_unchanged(target, old)):
                conflicts.add(relative)
                if _desired_conflict_is_blocking(relative):
                    blocking_conflicts.add(relative)
                if old:
                    entries[relative] = dict(old)
                continue

        changed |= _atomic_write(
            target,
            specification.content,
            specification.mode,
            allow_unsafe_existing_parent=project_parent,
        )
        if not relative.startswith(_STATE_PREFIX) and relative != _CONFIG_PATH:
            entries[relative] = _entry(
                relative, target, specification.owner, specification.strategy
            )

    changed |= _harden_existing_state_directories(paths.state)

    cleanup_changed, cleanup_conflicts = _cleanup_legacy_payload(workspace, source)
    changed |= cleanup_changed
    conflicts.update(cleanup_conflicts)

    # Host renderers consume only the canonical payload written above.  The
    # import is deliberately late so the install core remains independent of
    # host syntax and host_adapters can inspect the previous manifest.
    from solomon_harness.host_adapters import compile_adapters

    adapter_result = compile_adapters(workspace)
    changed |= adapter_result.changed
    conflicts.update(adapter_result.conflicts)
    blocking_conflicts.update(adapter_result.conflicts)
    for relative in adapter_result.conflicts:
        if relative in previous_entries:
            entries[relative] = dict(previous_entries[relative])
    for relative in adapter_result.managed_paths:
        target = _confined_path(workspace, relative)
        if target.is_file():
            entries[relative] = _compiled_adapter_entry(
                relative,
                target,
                previous_entries,
                snapshot,
            )

    removed: list[str] = []
    protected = {paths.root, paths.agents_root, paths.solomon, paths.config_dir, paths.state}
    for relative, old in sorted(previous_entries.items()):
        if relative in entries or relative in conflicts:
            continue
        target = _confined_path(workspace, relative)
        if (
            not target.is_file()
            or relative == _CONFIG_PATH
            or relative.startswith(_STATE_PREFIX)
            or old.get("owner") == "project"
        ):
            continue
        if _owned_entry_is_unchanged(target, old):
            target.unlink()
            record_install_mutation(target)
            removed.append(relative)
            changed = True
            _remove_empty_parents(target, workspace, protected)
        else:
            conflicts.add(relative)
            entries[relative] = dict(old)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "layout_version": LAYOUT_VERSION,
        "harness_version": _harness_version(source),
        "hosts": list(HOSTS),
        "migrations": [
            "canonical-handoffs-to-state",
            "legacy-agent-config",
            "legacy-memory-state",
            "legacy-solomon-state",
        ],
        "entries": [entries[name] for name in sorted(entries)],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    changed |= _atomic_write(paths.manifest, manifest_bytes, 0o644)
    return InstallResult(
        changed=changed,
        conflicts=tuple(sorted(conflicts)),
        removed=tuple(sorted(removed)),
        manifest_path=paths.manifest,
        blocking_conflicts=tuple(sorted(blocking_conflicts)),
    )


def compile_project_adapters(root: str | Path) -> InstallResult:
    """Reconcile an installed consumer's host adapters transactionally.

    Unlike an install or upgrade, compilation treats the existing canonical
    catalog as its input. It therefore updates only ``owner=adapter`` manifest
    entries and preserves every core and project entry byte-for-byte.
    """

    workspace = Path(root).expanduser().resolve()
    paths = HarnessPaths(workspace)
    with non_materializing_operation_lock(workspace):
        manifest = load_manifest(workspace)
        if not manifest:
            raise InstallConflictError(
                "Adapter compilation requires a valid installed manifest"
            )
        previous_entries = _manifest_entries(manifest)
        snapshot = _RollbackSnapshot(
            workspace,
            _transaction_targets(workspace, workspace, {}, previous_entries),
        )
        try:
            with observe_install_mutations(
                snapshot.checkpoint,
                publication_observer=snapshot.checkpoint_publication,
                root=workspace,
            ):
                with install_operation_lock(workspace):
                    return _apply_adapter_compile(
                        workspace,
                        paths,
                        manifest,
                        previous_entries,
                        snapshot,
                    )
        except BaseException as exc:
            rollback_conflicts = snapshot.rollback()
            if rollback_conflicts:
                detail = ", ".join(rollback_conflicts)
                raise InstallConflictError(
                    "Rollback preserved paths changed outside the compile "
                    f"transaction: {detail}"
                ) from exc
            raise


def register_agent_extension(
    root: str | Path,
    agent_name: str,
    mutation: Callable[[Path], None],
) -> Path:
    """Run one installed-agent scaffold and adapter compile atomically.

    The source directory is consumer-owned and intentionally absent from the
    install manifest. The surrounding transaction nevertheless snapshots its
    fixed scaffold shape together with every adapter/manifest target so a
    failed or conflicting compile restores the exact pre-registration state.
    """

    if re.fullmatch(r"[a-z0-9_]+", agent_name) is None:
        raise ValueError("Agent name must be alphanumeric and underscores only (snake_case)")

    declared_paths = HarnessPaths(root)
    workspace = declared_paths.root.resolve()
    paths = HarnessPaths(workspace)
    with non_materializing_operation_lock(workspace):
        from solomon_harness.host_adapter_common import is_harness_source_checkout

        if is_harness_source_checkout(workspace):
            raise InstallConflictError(
                "Direct agent registration is not allowed in a "
                "solomon-harness source checkout"
            )

        manifest = load_manifest(workspace)
        if not manifest:
            raise InstallConflictError(
                "Direct agent registration requires a valid installed harness manifest"
            )

        agents_relative = paths.agents.relative_to(workspace).as_posix()
        agents_path = _confined_path(workspace, agents_relative)
        if not agents_path.is_dir():
            raise InstallConflictError(
                "Direct agent registration requires the canonical installed agent catalog"
            )

        entries = _manifest_entries(manifest)
        required_core = (
            paths.rules,
            paths.pyproject,
            paths.python_package / "install_layout.py",
        )
        valid_identity = bool(
            manifest.get("layout_version") == LAYOUT_VERSION
            and manifest.get("hosts") == list(HOSTS)
            and isinstance(manifest.get("harness_version"), str)
            and manifest.get("harness_version")
        )
        for required in required_core:
            relative = required.relative_to(workspace).as_posix()
            entry = entries.get(relative)
            valid_identity = bool(
                valid_identity
                and entry is not None
                and entry.get("owner") == "core"
                and required.is_file()
                and _owned_entry_is_unchanged(required, entry)
            )
        if not valid_identity:
            raise InstallConflictError(
                "Direct agent registration requires a complete installed harness identity"
            )

        agent_path = _confined_path(
            workspace,
            (paths.agents / agent_name).relative_to(workspace).as_posix(),
        )
        targets = _transaction_targets(workspace, workspace, {}, entries)
        registration_relatives = (
            f".agents/solomon/agents/{agent_name}/persona.md",
            f".agents/solomon/agents/{agent_name}/main.py",
            f".agents/solomon/agents/{agent_name}/.agent/config.json",
            f".agents/solomon/agents/{agent_name}/agents/{agent_name}.md",
            f".agents/solomon/agents/{agent_name}/skills/scope_and_mandate.md",
            f".agents/agents/{agent_name}/agent.md",
            f".claude/agents/{agent_name}.md",
            f".codex/agents/{agent_name}.toml",
        )
        targets.update(
            _confined_path(workspace, relative)
            for relative in registration_relatives
        )
        snapshot = _RollbackSnapshot(workspace, targets)
        try:
            with observe_install_mutations(
                snapshot.checkpoint,
                publication_observer=snapshot.checkpoint_publication,
                root=workspace,
            ):
                with install_operation_lock(workspace):
                    mutation(agent_path)
                    compile_result = _apply_adapter_compile(
                        workspace,
                        paths,
                        manifest,
                        entries,
                        snapshot,
                    )
                    if compile_result.conflicts:
                        raise InstallConflictError(
                            "Agent adapter conflicts prevented registration: "
                            + ", ".join(compile_result.conflicts)
                        )
                    _validate_registered_agent(
                        workspace,
                        paths,
                        agent_name,
                        agent_path,
                    )
        except BaseException as exc:
            rollback_conflicts = snapshot.rollback()
            if rollback_conflicts:
                detail = ", ".join(rollback_conflicts)
                raise InstallConflictError(
                    "Rollback preserved paths changed outside the agent "
                    f"registration transaction: {detail}"
                ) from exc
            raise
        return declared_paths.agents / agent_name


def _validate_registered_agent(
    workspace: Path,
    paths: HarnessPaths,
    agent_name: str,
    agent_path: Path,
) -> None:
    """Fail closed unless source, adapters, and ownership are complete."""

    required_source = tuple(
        _confined_path(workspace, relative)
        for relative in (
            f".agents/solomon/agents/{agent_name}/persona.md",
            f".agents/solomon/agents/{agent_name}/main.py",
            f".agents/solomon/agents/{agent_name}/.agent/config.json",
            f".agents/solomon/agents/{agent_name}/agents/{agent_name}.md",
            f".agents/solomon/agents/{agent_name}/skills/scope_and_mandate.md",
        )
    )
    if (
        not agent_path.is_dir()
        or agent_path.is_symlink()
        or any(path.is_symlink() or not path.is_file() for path in required_source)
    ):
        raise InstallConflictError(
            f"Installed agent scaffold is incomplete: {agent_path}"
        )

    manifest = load_manifest(workspace)
    entries = _manifest_entries(manifest)
    adapters = tuple(
        _confined_path(workspace, relative)
        for relative in (
            f".agents/agents/{agent_name}/agent.md",
            f".claude/agents/{agent_name}.md",
            f".codex/agents/{agent_name}.toml",
        )
    )
    for adapter in adapters:
        relative = adapter.relative_to(workspace).as_posix()
        entry = entries.get(relative)
        if (
            not adapter.is_file()
            or entry is None
            or entry.get("owner") != "adapter"
        ):
            raise InstallConflictError(
                f"Installed agent adapter registration is incomplete: {relative}"
            )


def _apply_adapter_compile(
    workspace: Path,
    paths: HarnessPaths,
    manifest: dict[str, Any],
    previous_entries: dict[str, dict[str, Any]],
    snapshot: _RollbackSnapshot,
) -> InstallResult:
    """Compile adapters and atomically refresh their ownership records."""

    from solomon_harness.host_adapters import compile_adapters

    adapter_result = compile_adapters(workspace)
    entries = {relative: dict(entry) for relative, entry in previous_entries.items()}
    conflicts = set(adapter_result.conflicts)
    managed = set(adapter_result.managed_paths)

    for relative in sorted(managed):
        target = _confined_path(workspace, relative)
        if target.is_symlink() or not target.is_file():
            conflicts.add(relative)
            continue
        entries[relative] = _compiled_adapter_entry(
            relative,
            target,
            previous_entries,
            snapshot,
        )

    changed = adapter_result.changed
    removed: list[str] = []
    protected = {paths.root, paths.agents_root, paths.solomon, paths.config_dir, paths.state}
    for relative, previous in sorted(previous_entries.items()):
        if (
            previous.get("owner") != "adapter"
            or relative in managed
            or relative in conflicts
        ):
            continue
        target = _confined_path(workspace, relative)
        if not target.exists():
            entries.pop(relative, None)
            continue
        if target.is_symlink() or not target.is_file():
            conflicts.add(relative)
            continue

        strategy = previous.get("strategy")
        if strategy in {"json-merge", "toml-merge", "marker-merge"}:
            if not _managed_adapter_is_unchanged(target, relative, previous):
                conflicts.add(relative)
                continue
            adapter_changed, empty = _remove_merged_adapter(target, relative)
            changed |= adapter_changed
            if empty and previous.get("created"):
                target.unlink(missing_ok=True)
                record_install_mutation(target)
                _remove_empty_parents(target, workspace, protected)
                changed = True
        else:
            if not _owned_entry_is_unchanged(target, previous):
                conflicts.add(relative)
                continue
            target.unlink()
            record_install_mutation(target)
            _remove_empty_parents(target, workspace, protected)
            changed = True
        entries.pop(relative, None)
        removed.append(relative)

    updated_manifest = dict(manifest)
    updated_manifest["entries"] = [entries[name] for name in sorted(entries)]
    manifest_bytes = (
        json.dumps(updated_manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    changed |= _atomic_write(paths.manifest, manifest_bytes, 0o644)
    ordered_conflicts = tuple(sorted(conflicts))
    return InstallResult(
        changed=changed,
        conflicts=ordered_conflicts,
        removed=tuple(sorted(removed)),
        manifest_path=paths.manifest,
        blocking_conflicts=ordered_conflicts,
    )


def migrate_layout(
    root: str | Path,
    *,
    source_root: str | Path | None = None,
) -> InstallResult:
    """Migrate legacy paths and finish installation in the canonical layout."""

    workspace = Path(root).expanduser().resolve()
    return install_project(workspace, source_root=source_root)


def _remove_marked_block(path: Path, start: str, end: str) -> tuple[bool, bool]:
    """Remove one Solomon marker block and report ``(changed, now_empty)``."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallConflictError(f"Cannot parse managed adapter {path}") from exc
    has_start = start in text
    has_end = end in text
    if has_start != has_end:
        raise InstallConflictError(f"Managed markers are incomplete in {path}")
    if not has_start:
        return False, not text.strip()
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    cleaned = before.rstrip()
    trailing = after.lstrip("\n")
    if cleaned and trailing:
        cleaned += "\n\n" + trailing
    elif trailing:
        cleaned = trailing
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    changed = _atomic_write(path, cleaned.encode(), _mode(path))
    return changed, not cleaned.strip()


def _remove_json_adapter(path: Path, relative: str) -> tuple[bool, bool]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallConflictError(f"Cannot parse managed JSON adapter {path}") from exc
    if not isinstance(document, dict):
        raise InstallConflictError(f"Managed JSON adapter is not an object: {path}")
    before = json.dumps(document, sort_keys=True)

    if relative in {".claude/settings.json", ".codex/hooks.json"}:
        host = "claude" if relative == ".claude/settings.json" else "codex"
        hooks = document.get("hooks")
        if isinstance(hooks, dict):
            for event in list(hooks):
                values = hooks[event]
                if isinstance(values, list):
                    hooks[event] = [
                        item for item in values if not _contains_solomon_hook(item, host=host)
                    ]
                    if not hooks[event]:
                        hooks.pop(event)
            if not hooks:
                document.pop("hooks", None)
    elif relative == ".agents/hooks.json":
        document.pop("solomon-session-resume", None)
        document.pop("solomon-loop-guard", None)
    elif relative in {
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".mcp.json",
    }:
        servers = document.get("mcpServers")
        if isinstance(servers, dict):
            servers.pop("solomon-memory", None)
            if not servers:
                document.pop("mcpServers", None)

    after = json.dumps(document, sort_keys=True)
    if before == after:
        return False, not document
    changed = _atomic_write(
        path,
        (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        _mode(path),
    )
    return changed, not document


def _remove_merged_adapter(path: Path, relative: str) -> tuple[bool, bool]:
    if relative in {"AGENTS.md", ".claude/CLAUDE.md"}:
        return _remove_marked_block(path, _TEXT_START, _TEXT_END)
    if relative == ".codex/config.toml":
        return _remove_marked_block(path, _TOML_START, _TOML_END)
    return _remove_json_adapter(path, relative)


def _managed_adapter_is_unchanged(
    path: Path,
    relative: str,
    entry: dict[str, Any],
) -> bool:
    try:
        expected_mode = int(str(entry.get("mode", "")), 8)
    except ValueError:
        return False
    if _mode(path) != expected_mode:
        return False
    expected = entry.get("managed_sha256")
    if isinstance(expected, str):
        try:
            return _managed_adapter_digest(path, relative) == expected
        except (AdapterOwnershipError, InstallConflictError):
            return False
    return _owned_entry_is_unchanged(path, entry)


def uninstall_project(root: str | Path) -> InstallResult:
    """Remove unchanged owned files while retaining state, config, and user edits."""

    paths = HarnessPaths(root)
    with non_materializing_operation_lock(paths.root):
        if not load_manifest(paths.root):
            return InstallResult(False, manifest_path=paths.manifest)
        with install_operation_lock(paths.root):
            return _uninstall_project_locked(paths)


def _uninstall_project_locked(paths: HarnessPaths) -> InstallResult:
    """Apply one uninstall while the workspace operation lock is held."""

    manifest = load_manifest(paths.root)
    if not manifest:
        return InstallResult(False, manifest_path=paths.manifest)
    entries = _manifest_entries(manifest)
    conflicts: list[str] = []
    removed: list[str] = []
    remaining: dict[str, dict[str, Any]] = {}
    changed = False
    protected = {paths.root, paths.agents_root, paths.solomon, paths.config_dir, paths.state}

    # Validate the complete manifest before deleting the first file.
    targets = {relative: _confined_path(paths.root, relative) for relative in entries}
    for relative in sorted(entries, reverse=True):
        if (
            relative == _CONFIG_PATH
            or relative.startswith(_STATE_PREFIX)
            or entries[relative].get("owner") == "project"
        ):
            continue
        target = targets[relative]
        if not target.exists():
            continue
        if target.is_symlink() or not target.is_file():
            conflicts.append(relative)
            remaining[relative] = entries[relative]
            continue
        strategy = entries[relative].get("strategy")
        if strategy in {"json-merge", "toml-merge", "marker-merge"}:
            if not _managed_adapter_is_unchanged(
                target,
                relative,
                entries[relative],
            ):
                conflicts.append(relative)
                remaining[relative] = entries[relative]
                continue
            try:
                adapter_changed, empty = _remove_merged_adapter(target, relative)
            except InstallConflictError:
                conflicts.append(relative)
                remaining[relative] = entries[relative]
                continue
            changed |= adapter_changed
            if empty and entries[relative].get("created"):
                target.unlink(missing_ok=True)
                _remove_empty_parents(target, paths.root, protected)
                changed = True
            removed.append(relative)
            continue
        if not _owned_entry_is_unchanged(target, entries[relative]):
            conflicts.append(relative)
            remaining[relative] = entries[relative]
            continue
        target.unlink()
        removed.append(relative)
        changed = True
        _remove_empty_parents(target, paths.root, protected)

    if conflicts:
        partial_manifest = dict(manifest)
        partial_manifest["entries"] = [remaining[name] for name in sorted(remaining)]
        manifest_bytes = (json.dumps(partial_manifest, indent=2, sort_keys=True) + "\n").encode()
        changed |= _atomic_write(paths.manifest, manifest_bytes, 0o644)
        return InstallResult(
            changed=changed,
            conflicts=tuple(sorted(conflicts)),
            removed=tuple(sorted(removed)),
            manifest_path=paths.manifest,
        )
    paths.manifest.unlink(missing_ok=True)
    _remove_empty_parents(paths.manifest, paths.root, protected)
    return InstallResult(
        changed=changed or bool(removed),
        removed=tuple(sorted(removed)),
        manifest_path=paths.manifest,
    )
