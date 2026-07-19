"""Cross-process serialization for repository-local harness mutations."""

from __future__ import annotations

import hashlib
import os
import importlib
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator

from solomon_harness.install_transaction import (
    ensure_install_directory,
    record_install_mutation,
)
from solomon_harness.layout import HarnessPaths, PathLike, confined_path


_LOCK_NAME = "install.lock"
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_registry_guard = threading.Lock()
_process_locks: dict[str, threading.RLock] = {}
_thread_state = threading.local()


def operation_lock_path(root: PathLike) -> Path:
    """Return the confined lock path shared by every mutating install operation."""

    paths = HarnessPaths(root)
    return confined_path(paths.root, paths.state / _LOCK_NAME)


def _process_lock(key: str) -> threading.RLock:
    with _registry_guard:
        return _process_locks.setdefault(key, threading.RLock())


def _anchor_path(root: PathLike) -> Path:
    """Return stable operational coordination state outside the repository."""

    workspace = Path(root).expanduser().resolve()
    digest = hashlib.sha256(os.fsencode(workspace)).hexdigest()
    uid = str(os.getuid()) if hasattr(os, "getuid") else "user"
    directory = Path(tempfile.gettempdir()) / f"solomon-harness-locks-{uid}"
    if directory.exists() or directory.is_symlink():
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Install anchor parent is unsafe: {directory}")
        if os.name != "nt":
            info = directory.stat()
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ValueError(f"Install anchor parent has a different owner: {directory}")
            if stat.S_IMODE(info.st_mode) != _PRIVATE_DIRECTORY_MODE:
                os.chmod(directory, _PRIVATE_DIRECTORY_MODE)
    else:
        directory.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
        if os.name != "nt":
            os.chmod(directory, _PRIVATE_DIRECTORY_MODE)
    return directory / f"{digest}.lock"


def _open_anchor(path: Path) -> BinaryIO:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Install anchor is not a regular file: {path}")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, _PRIVATE_FILE_MODE)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "r+b", buffering=0)


def _open_lock(root: Path, path: Path) -> BinaryIO:
    paths = HarnessPaths(root)
    ensure_install_directory(
        paths.root,
        path.parent,
        private_root=paths.state,
    )
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Install lock is not a regular file: {path}")
    existed = path.is_file()
    previous_mode = stat.S_IMODE(path.stat().st_mode) if existed else None
    previous_size = path.stat().st_size if existed else None
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, _PRIVATE_FILE_MODE)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if (
            not existed
            or previous_mode != _PRIVATE_FILE_MODE
            or previous_size == 0
        ):
            record_install_mutation(path)
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "r+b", buffering=0)


def _acquire_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        windows_locking: Any = importlib.import_module("msvcrt")
        windows_locking.locking(stream.fileno(), windows_locking.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        windows_locking: Any = importlib.import_module("msvcrt")
        stream.seek(0)
        windows_locking.locking(stream.fileno(), windows_locking.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _serialized_file_lock(
    key: str,
    opener: Callable[[], BinaryIO],
) -> Iterator[None]:
    """Acquire one process/thread reentrant advisory-file lock."""

    local_lock = _process_lock(key)
    local_lock.acquire()
    depths = getattr(_thread_state, "depths", None)
    if depths is None:
        depths = {}
        _thread_state.depths = depths
    handles = getattr(_thread_state, "handles", None)
    if handles is None:
        handles = {}
        _thread_state.handles = handles

    try:
        depth = int(depths.get(key, 0))
        if depth == 0:
            stream = opener()
            try:
                _acquire_file_lock(stream)
            except BaseException:
                stream.close()
                raise
            handles[key] = stream
        depths[key] = depth + 1
        yield
    finally:
        depth = int(depths.get(key, 1)) - 1
        if depth == 0:
            depths.pop(key, None)
            stream = handles.pop(key, None)
            if stream is not None:
                try:
                    _release_file_lock(stream)
                finally:
                    stream.close()
        else:
            depths[key] = depth
        local_lock.release()


@contextmanager
def non_materializing_operation_lock(root: PathLike) -> Iterator[Path]:
    """Serialize a preflight without creating repository-local payload state.

    The stable anchor lives in the operating-system temporary directory and is
    coordination metadata, never installed payload. Every mutating operation
    acquires this anchor before the canonical lock, preventing split-brain when
    a failed fresh operation rolls the canonical lock back out of the project.
    """

    anchor = _anchor_path(root)
    key = f"anchor:{os.fspath(anchor)}"
    with _serialized_file_lock(key, lambda: _open_anchor(anchor)):
        yield operation_lock_path(root)


@contextmanager
def install_operation_lock(root: PathLike) -> Iterator[Path]:
    """Serialize and materialize canonical install coordination state."""

    workspace = Path(root).expanduser().resolve()
    path = operation_lock_path(workspace)
    with non_materializing_operation_lock(workspace):
        key = f"canonical:{os.fspath(path)}"
        with _serialized_file_lock(key, lambda: _open_lock(workspace, path)):
            yield path


__all__ = [
    "install_operation_lock",
    "non_materializing_operation_lock",
    "operation_lock_path",
]
