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
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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
_TEXT_START = "<!-- solomon-harness:start -->"
_TEXT_END = "<!-- solomon-harness:end -->"
_TOML_START = "# >>> solomon-harness managed adapter >>>"
_TOML_END = "# <<< solomon-harness managed adapter <<<"
_UV_ENVIRONMENT = "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv"
_UV_PROJECT = "uv run --project .agents/solomon"
_HARNESS_RUN = f"{_UV_ENVIRONMENT} {_UV_PROJECT}"
# Cleanup proofs intentionally cover only the immediately preceding release.
_LEGACY_PROOF_FILES = (Path("solomon_harness/legacy_payloads/v0.11.0.tsv"),)
_LEGACY_SIGNATURE_PATHS = (
    Path("agents/flutter/skills/navigation.md"),
    Path("scripts/git-hooks/pre-commit"),
    Path("solomon_harness/notify.py"),
)


class InstallConflictError(RuntimeError):
    """Raised when installer metadata is invalid or escapes the workspace."""


@dataclass(frozen=True)
class InstallResult:
    """Summary of an install, migration, upgrade, or uninstall operation."""

    changed: bool
    conflicts: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    manifest_path: Path | None = None


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


class _RollbackSnapshot:
    """Capture only paths the installer may mutate and restore them on error."""

    def __init__(self, root: Path, targets: Iterable[Path]) -> None:
        self.root = root
        self.files: dict[Path, _FileSnapshot] = {}
        self.existing_directories: set[Path] = {root}
        self.candidate_directories: set[Path] = set()
        for path in sorted(set(targets)):
            parent = path.parent
            while parent != root and parent not in self.candidate_directories:
                self.candidate_directories.add(parent)
                if parent.is_dir() and not parent.is_symlink():
                    self.existing_directories.add(parent)
                parent = parent.parent
            if path.is_symlink():
                self.files[path] = _FileSnapshot("symlink", os.readlink(path))
            elif path.is_file():
                info = path.stat()
                self.files[path] = _FileSnapshot(
                    "file",
                    path.read_bytes(),
                    stat.S_IMODE(info.st_mode),
                    info.st_atime_ns,
                    info.st_mtime_ns,
                )
            elif path.is_dir():
                self.files[path] = _FileSnapshot("directory")
                self.existing_directories.add(path)
            else:
                self.files[path] = _FileSnapshot("missing")

    @staticmethod
    def _remove_current(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    def rollback(self) -> None:
        for path, snapshot in self.files.items():
            if snapshot.kind == "missing":
                self._remove_current(path)
                continue
            if snapshot.kind == "directory":
                path.mkdir(parents=True, exist_ok=True)
                continue
            self._remove_current(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if snapshot.kind == "symlink":
                path.symlink_to(str(snapshot.content))
                continue
            path.write_bytes(snapshot.content if isinstance(snapshot.content, bytes) else b"")
            os.chmod(path, snapshot.mode)
            os.utime(path, ns=(snapshot.atime_ns, snapshot.mtime_ns))

        for directory in sorted(
            self.candidate_directories - self.existing_directories,
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass


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
        (".claude/agents/", ".agents/solomon/agents/"),
        ("solomon_harness/catalog/workflows/", ".agents/solomon/workflows/"),
        ("docs/solomon-workflow.md", ".agents/solomon/conventions/solomon-workflow.md"),
        ("docs/release-policy.md", ".agents/solomon/conventions/release-policy.md"),
        ("docs/loop-engineering.md", ".agents/solomon/conventions/loop-engineering.md"),
        ("agents/AGENTS.md", ".agents/solomon/AGENTS.md"),
        (".agent/config.json", ".agents/solomon/config/project.json"),
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
        "uv run python -m solomon_harness",
        f"{_HARNESS_RUN} python -m solomon_harness",
    )
    text = text.replace(
        "uv run python .agents/solomon/scripts/",
        f"{_HARNESS_RUN} python .agents/solomon/scripts/",
    )
    text = text.replace(
        'uv run python -c "import solomon_harness"',
        f'{_HARNESS_RUN} python -c "import solomon_harness"',
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


def _atomic_write(path: Path, content: bytes, mode: int) -> bool:
    if path.is_symlink():
        raise InstallConflictError(f"Refusing to replace symlink: {path}")
    if path.is_file() and path.read_bytes() == content and _mode(path) == mode:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
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


def _remove_empty_parents(path: Path, root: Path, protected: set[Path]) -> None:
    parent = path.parent
    while parent != root and parent not in protected:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _validate_legacy_paths(paths: HarnessPaths) -> None:
    """Reject legacy migration sources that traverse any symlink."""

    if paths.legacy_config.exists() or paths.legacy_config.is_symlink():
        _confined_path(paths.root, paths.legacy_config.relative_to(paths.root).as_posix())
    if not (paths.legacy_state.exists() or paths.legacy_state.is_symlink()):
        return
    _confined_path(paths.root, paths.legacy_state.relative_to(paths.root).as_posix())
    if paths.legacy_state.is_dir():
        for source in paths.legacy_state.rglob("*"):
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
    if relative.parts[0] in {"agents", "scripts", "solomon_harness"}:
        return True
    return relative.parts[:2] == (".claude", "commands")


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
    if not set(_LEGACY_SIGNATURE_PATHS) <= set(proofs):
        raise InstallConflictError(
            f"Legacy payload proof catalog lacks its signatures: {catalog_relative}"
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


def _cleanup_legacy_payload(root: Path, source_root: Path) -> tuple[bool, tuple[str, ...]]:
    """Remove only byte-and-mode-identical files from the former root layout."""

    if root.resolve() == source_root.resolve():
        return False, ()
    conflicts = _unowned_gemini_paths(root)
    proofs = _recognized_legacy_payload_proofs(root, source_root)
    if not proofs:
        for relative in _LEGACY_SIGNATURE_PATHS:
            if (root / relative).exists():
                conflicts.add(relative.as_posix())
        return False, tuple(sorted(conflicts))

    changed = False
    cleanup_roots = (
        root / "agents",
        root / "scripts",
        root / "solomon_harness",
        root / ".claude" / "commands",
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
            candidates = proofs.get(relative, set())
            if target.is_symlink() or not any(
                _matches_payload_proof(root, relative, proof) for proof in candidates
            ):
                conflicts.add(relative.as_posix())
                continue
            target.unlink()
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
        try:
            cleanup_root.rmdir()
        except OSError:
            pass

    return changed, tuple(sorted(conflicts))


def _migrate_legacy(root: Path) -> tuple[bool, tuple[str, ...]]:
    paths = HarnessPaths(root)
    _validate_legacy_paths(paths)
    handoff_pairs = _handoff_migration_pairs(paths)
    changed = False
    conflicts: list[str] = []

    for source, target in handoff_pairs:
        if not target.exists():
            changed |= _atomic_write(target, source.read_bytes(), _mode(source))
            source.unlink()
            changed = True
        elif _same_payload_file(target, source):
            source.unlink()
            changed = True
        else:
            conflicts.append(_relative(root, source))

    if paths.legacy_config.is_file():
        content = paths.legacy_config.read_bytes()
        if not paths.config.exists():
            changed |= _atomic_write(paths.config, content, _mode(paths.legacy_config))
            paths.legacy_config.unlink()
            changed = True
        elif paths.config.read_bytes() == content:
            paths.legacy_config.unlink()
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
            if not target.exists():
                changed |= _atomic_write(target, source.read_bytes(), _mode(source))
                source.unlink()
                changed = True
            elif _same_payload_file(target, source):
                source.unlink()
                changed = True
            else:
                conflicts.append(_relative(root, source))

    for legacy in (
        paths.legacy_config.parent,
        paths.legacy_state,
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
        try:
            legacy.rmdir()
            changed = True
        except OSError:
            pass

    return changed, tuple(sorted(set(conflicts)))


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


def _contains_solomon_hook(value: Any, *, host: str) -> bool:
    text = json.dumps(value, sort_keys=True)
    return "solomon_harness.cli host-hook" in text and f"--host {host}" in text


def _marked_fragment(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise InstallConflictError("Managed adapter markers are missing or ambiguous")
    _, remainder = text.split(start, 1)
    managed, _ = remainder.split(end, 1)
    return f"{start}{managed}{end}"


def _managed_json_fragment(document: dict[str, Any], relative: str) -> Any:
    if relative in {".claude/settings.json", ".codex/hooks.json"}:
        host = "claude" if relative == ".claude/settings.json" else "codex"
        hooks = document.get("hooks")
        managed: dict[str, list[Any]] = {}
        if isinstance(hooks, dict):
            for event in sorted(hooks):
                values = hooks[event]
                if not isinstance(values, list):
                    continue
                nodes = [item for item in values if _contains_solomon_hook(item, host=host)]
                if nodes:
                    managed[event] = nodes
        return {"hooks": managed}
    if relative == ".agents/hooks.json":
        names = ("solomon-loop-guard", "solomon-session-resume")
        return {name: document[name] for name in names if name in document}
    if relative in {
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".mcp.json",
    }:
        servers = document.get("mcpServers")
        value = servers.get("solomon-memory") if isinstance(servers, dict) else None
        return {"mcpServers": {"solomon-memory": value}}
    raise InstallConflictError(f"Unsupported managed JSON adapter: {relative}")


def _managed_adapter_digest(path: Path, relative: str) -> str:
    strategy = _strategy_for_adapter(relative)
    try:
        if strategy == "marker-merge":
            fragment = _marked_fragment(
                path.read_text(encoding="utf-8"),
                _TEXT_START,
                _TEXT_END,
            )
            content = fragment.encode()
        elif strategy == "toml-merge":
            fragment = _marked_fragment(
                path.read_text(encoding="utf-8"),
                _TOML_START,
                _TOML_END,
            )
            content = fragment.encode()
        elif strategy == "json-merge":
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise InstallConflictError(f"Managed JSON adapter is not an object: {path}")
            fragment = _managed_json_fragment(document, relative)
            content = json.dumps(
                fragment,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        else:
            raise InstallConflictError(f"Adapter is not merge-managed: {relative}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallConflictError(f"Cannot inspect managed adapter {path}") from exc
    return _sha256(content)


def _strategy_for_adapter(relative: str) -> str:
    if relative in {
        ".claude/settings.json",
        ".mcp.json",
        ".agents/hooks.json",
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".codex/hooks.json",
    }:
        return "json-merge"
    if relative == ".codex/config.toml":
        return "toml-merge"
    if relative in {"AGENTS.md", ".claude/CLAUDE.md"}:
        return "marker-merge"
    return "replace"


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
    """Install or upgrade the harness in ``root`` without overwriting user edits."""

    workspace = Path(root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
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
        return _apply_install(workspace, source, paths, previous_entries, desired, snapshot)
    except BaseException:
        snapshot.rollback()
        raise


def _apply_install(
    workspace: Path,
    source: Path,
    paths: HarnessPaths,
    previous_entries: dict[str, dict[str, Any]],
    desired: dict[str, _DesiredFile],
    snapshot: _RollbackSnapshot,
) -> InstallResult:
    changed, migration_conflicts = _migrate_legacy(workspace)
    conflicts = set(migration_conflicts)
    entries: dict[str, dict[str, Any]] = {}

    for relative, specification in sorted(desired.items()):
        target = _confined_path(workspace, relative)
        old = previous_entries.get(relative)
        desired_hash = _sha256(specification.content)

        if specification.strategy == "create-only" and target.exists():
            if target.is_symlink() or not target.is_file():
                conflicts.add(relative)
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
            if old:
                entries[relative] = dict(old)
            continue

        if target.is_file():
            matches_desired = (
                _sha256(target.read_bytes()) == desired_hash and _mode(target) == specification.mode
            )
            if not matches_desired and (old is None or not _owned_entry_is_unchanged(target, old)):
                conflicts.add(relative)
                if old:
                    entries[relative] = dict(old)
                continue

        changed |= _atomic_write(target, specification.content, specification.mode)
        if not relative.startswith(_STATE_PREFIX) and relative != _CONFIG_PATH:
            entries[relative] = _entry(
                relative, target, specification.owner, specification.strategy
            )

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
    for relative in adapter_result.conflicts:
        if relative in previous_entries:
            entries[relative] = dict(previous_entries[relative])
    for relative in adapter_result.managed_paths:
        target = _confined_path(workspace, relative)
        if target.is_file():
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
            else:
                original = snapshot.files.get(target, _FileSnapshot("missing"))
                adapter_entry["created"] = original.kind == "missing"
                if original.kind == "file" and isinstance(original.content, bytes):
                    adapter_entry["base_sha256"] = _sha256(original.content)
            entries[relative] = adapter_entry

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
    )


def migrate_layout(
    root: str | Path,
    *,
    source_root: str | Path | None = None,
) -> InstallResult:
    """Migrate legacy paths and finish installation in the canonical layout."""

    return install_project(root, source_root=source_root)


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
        except InstallConflictError:
            return False
    return _owned_entry_is_unchanged(path, entry)


def uninstall_project(root: str | Path) -> InstallResult:
    """Remove unchanged owned files while retaining state, config, and user edits."""

    paths = HarnessPaths(root)
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
