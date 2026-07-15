"""Transaction-local observation for repository install mutations."""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Callable, Iterator


MutationObserver = Callable[[Path], None]
_observer: ContextVar[MutationObserver | None] = ContextVar(
    "solomon_install_mutation_observer",
    default=None,
)
_root: ContextVar[Path | None] = ContextVar(
    "solomon_install_transaction_root",
    default=None,
)


class UnsafeInstallDirectoryError(ValueError):
    """Raised when an install would trust an unsafe repository directory."""


@contextmanager
def observe_install_mutations(
    observer: MutationObserver,
    *,
    root: Path | None = None,
) -> Iterator[None]:
    """Route mutations in this execution context to ``observer``."""

    token: Token[MutationObserver | None] = _observer.set(observer)
    root_token: Token[Path | None] = _root.set(root.resolve() if root else None)
    try:
        yield
    finally:
        _root.reset(root_token)
        _observer.reset(token)


def record_install_mutation(path: Path) -> None:
    """Record a completed write or removal when an install transaction is active."""

    observer = _observer.get()
    if observer is not None:
        observer(path)


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
    "UnsafeInstallDirectoryError",
    "current_install_root",
    "ensure_install_directory",
    "ensure_install_parent",
    "observe_install_mutations",
    "record_install_mutation",
]
