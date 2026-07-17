"""Transaction-local observation for repository install mutations."""

from __future__ import annotations

import os
import stat
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator

from solomon_harness.layout import HarnessPaths


MutationObserver = Callable[[Path], None]
PublicationObserver = Callable[[Path, "InstallFilePublication"], None]
_observer: ContextVar[MutationObserver | None] = ContextVar(
    "solomon_install_mutation_observer",
    default=None,
)
_publication_observer: ContextVar[PublicationObserver | None] = ContextVar(
    "solomon_install_publication_observer",
    default=None,
)
_root: ContextVar[Path | None] = ContextVar(
    "solomon_install_transaction_root",
    default=None,
)


@dataclass(frozen=True)
class InstallFilePublication:
    """Exact regular-file state produced before an atomic publication."""

    content: bytes
    mode: int
    atime_ns: int
    mtime_ns: int
    device: int
    inode: int


class UnsafeInstallDirectoryError(ValueError):
    """Raised when an install would trust an unsafe repository directory."""


@contextmanager
def observe_install_mutations(
    observer: MutationObserver,
    *,
    publication_observer: PublicationObserver | None = None,
    root: Path | None = None,
) -> Iterator[None]:
    """Route mutations in this execution context to ``observer``."""

    token: Token[MutationObserver | None] = _observer.set(observer)
    inherited_publication = _publication_observer.get()
    publication_token: Token[PublicationObserver | None] = _publication_observer.set(
        publication_observer or inherited_publication
    )
    root_token: Token[Path | None] = _root.set(root.resolve() if root else None)
    try:
        yield
    finally:
        _root.reset(root_token)
        _publication_observer.reset(publication_token)
        _observer.reset(token)


def record_install_mutation(path: Path) -> None:
    """Record a completed write or removal when an install transaction is active."""

    observer = _observer.get()
    if observer is not None:
        observer(path)


def record_install_file_publication(
    path: Path,
    publication: InstallFilePublication,
) -> None:
    """Record an atomic publication without sampling a possibly replaced path."""

    observer = _publication_observer.get()
    if observer is not None:
        observer(path, publication)
        return
    record_install_mutation(path)


def _write_install_payload(stream: BinaryIO, payload: bytes) -> None:
    """Write and durably flush one temporary scaffold payload."""

    stream.write(payload)
    stream.flush()
    os.fsync(stream.fileno())


def _resolved_install_target(root: Path, path: Path) -> tuple[Path, Path]:
    """Resolve a declared-root alias while preserving lexical confinement."""

    declared = Path(os.path.abspath(os.fspath(root.expanduser())))
    candidate = path.expanduser()
    if ".." in candidate.parts:
        raise UnsafeInstallDirectoryError(
            f"Install file contains parent traversal: {path}"
        )
    absolute = (
        Path(os.path.abspath(os.fspath(candidate)))
        if candidate.is_absolute()
        else declared / candidate
    )
    try:
        relative = absolute.relative_to(declared)
    except ValueError as exc:
        raise UnsafeInstallDirectoryError(
            f"Install file escapes the workspace: {path}"
        ) from exc
    workspace = declared.resolve()
    return workspace, workspace.joinpath(*relative.parts)


def create_install_file(
    root: Path,
    path: Path,
    content: bytes,
    mode: int = 0o644,
) -> Path:
    """Atomically publish one create-only file with an exact rollback proof."""

    workspace, target = _resolved_install_target(root, path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Install file already exists: {target}")
    ensure_install_parent(
        workspace,
        target,
        private_root=HarnessPaths(workspace).state,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _write_install_payload(stream, content)
        os.chmod(temporary, mode)
        published_content = temporary.read_bytes()
        info = temporary.stat()
        publication = InstallFilePublication(
            content=published_content,
            mode=stat.S_IMODE(info.st_mode),
            atime_ns=info.st_atime_ns,
            mtime_ns=info.st_mtime_ns,
            device=info.st_dev,
            inode=info.st_ino,
        )
        os.link(temporary, target, follow_symlinks=False)
        record_install_file_publication(target, publication)
        if os.name != "nt":
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary_existed = temporary.exists()
        temporary.unlink(missing_ok=True)
        if temporary_existed:
            record_install_mutation(target.parent)
    return target


def current_install_root() -> Path | None:
    """Return the workspace owned by the active install transaction, if any."""

    return _root.get()


def ensure_install_directory(
    root: Path,
    path: Path,
    *,
    private_root: Path | None = None,
    allow_unsafe_existing: bool = False,
) -> None:
    """Create safe repository parents without rewriting tenant-owned modes.

    Newly created managed directories are published with an explicit ``0755``
    mode regardless of umask. The state subtree is explicitly ``0700``. An
    existing non-state directory that is group- or world-writable is rejected,
    because replacing a managed child would otherwise remain possible. Existing
    safe tenant directories retain their original mode.
    """

    workspace = root.resolve()
    target = path if path.is_absolute() else workspace / path
    try:
        relative = target.relative_to(workspace)
    except ValueError as exc:
        raise UnsafeInstallDirectoryError(
            f"Install directory escapes the workspace: {target}"
        ) from exc
    private = private_root if private_root is None or private_root.is_absolute() else workspace / private_root
    if private is not None:
        try:
            private.relative_to(workspace)
        except ValueError as exc:
            raise UnsafeInstallDirectoryError(
                f"Private install directory escapes the workspace: {private}"
            ) from exc

    current = workspace
    for part in relative.parts:
        current /= part
        is_private = private is not None and (
            current == private or private in current.parents
        )
        desired_mode = 0o700 if is_private else 0o755
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise UnsafeInstallDirectoryError(
                    f"Install directory traverses a symlink or non-directory: {current}"
                )
            if os.name == "nt":
                continue
            current_mode = stat.S_IMODE(current.stat().st_mode)
            if is_private:
                if current_mode != desired_mode:
                    os.chmod(current, desired_mode)
                    record_install_mutation(current)
            elif current_mode & 0o022 and not allow_unsafe_existing:
                raise UnsafeInstallDirectoryError(
                    f"Existing install directory has an unsafe writable mode "
                    f"{current_mode:04o}: {current}"
                )
            continue
        current.mkdir(mode=desired_mode)
        if os.name != "nt":
            os.chmod(current, desired_mode)
        record_install_mutation(current)


def ensure_install_parent(
    root: Path,
    path: Path,
    *,
    private_root: Path | None = None,
    allow_unsafe_existing: bool = False,
) -> None:
    """Ensure the parent of one transaction output satisfies the trust contract."""

    ensure_install_directory(
        root,
        path.parent,
        private_root=private_root,
        allow_unsafe_existing=allow_unsafe_existing,
    )


__all__ = [
    "InstallFilePublication",
    "UnsafeInstallDirectoryError",
    "create_install_file",
    "current_install_root",
    "ensure_install_directory",
    "ensure_install_parent",
    "observe_install_mutations",
    "record_install_file_publication",
    "record_install_mutation",
]
