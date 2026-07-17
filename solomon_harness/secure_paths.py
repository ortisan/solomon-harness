"""Directory-FD-anchored filesystem operations for generated harness artifacts."""

import os
import secrets
import stat
from typing import Optional


class UnsafePathError(ValueError):
    """Raised when a managed path is a symlink or an unexpected file type."""


def _validate_component(name: str) -> None:
    if not name or name in {".", ".."} or os.sep in name:
        raise UnsafePathError(f"unsafe path component: {name!r}")
    if os.altsep and os.altsep in name:
        raise UnsafePathError(f"unsafe path component: {name!r}")


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _same_entry(expected: os.stat_result, opened: os.stat_result) -> bool:
    return (expected.st_dev, expected.st_ino) == (opened.st_dev, opened.st_ino)


def open_root_directory(path: str) -> int:
    """Open the workspace anchor without following a final symlink."""
    try:
        descriptor = os.open(path, _directory_flags())
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise UnsafePathError(f"unsafe root directory: {path}") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise UnsafePathError(f"unsafe root directory: {path}")
    return descriptor


def stat_at(parent_fd: int, name: str) -> Optional[os.stat_result]:
    """lstat one child component relative to an already-open directory."""
    _validate_component(name)
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def open_directory_at(
    parent_fd: int,
    name: str,
    *,
    create: bool = False,
    missing_ok: bool = False,
    mode: int = 0o755,
) -> Optional[int]:
    """Open one child directory, optionally creating it, without symlink traversal."""
    entry = stat_at(parent_fd, name)
    if entry is None and create:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
        except FileExistsError:
            pass
        entry = stat_at(parent_fd, name)
    if entry is None:
        if missing_ok:
            return None
        raise FileNotFoundError(name)
    if not stat.S_ISDIR(entry.st_mode):
        raise UnsafePathError(f"unsafe directory component: {name}")
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafePathError(f"unsafe directory component: {name}") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or not _same_entry(entry, opened):
        os.close(descriptor)
        raise UnsafePathError(f"unsafe directory component: {name}")
    return descriptor


def open_regular_at(
    parent_fd: int,
    name: str,
    *,
    max_bytes: int = 0,
    missing_ok: bool = False,
) -> Optional[int]:
    """Open one regular child file with type, identity, and optional size checks."""
    entry = stat_at(parent_fd, name)
    if entry is None:
        if missing_ok:
            return None
        raise FileNotFoundError(name)
    if not stat.S_ISREG(entry.st_mode) or (max_bytes and entry.st_size > max_bytes):
        raise UnsafePathError(f"unsafe regular file: {name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafePathError(f"unsafe regular file: {name}") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or not _same_entry(entry, opened)
        or (max_bytes and opened.st_size > max_bytes)
    ):
        os.close(descriptor)
        raise UnsafePathError(f"unsafe regular file: {name}")
    return descriptor


def read_regular_at(parent_fd: int, name: str, *, max_bytes: int) -> bytes:
    """Read a bounded regular child file through its anchored descriptor."""
    descriptor = open_regular_at(parent_fd, name, max_bytes=max_bytes)
    assert descriptor is not None
    with os.fdopen(descriptor, "rb") as f:
        content = f.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise UnsafePathError(f"unsafe regular file: {name}")
    return content


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def create_regular_at(parent_fd: int, name: str, content: bytes, *, mode: int) -> bool:
    """Create a missing regular file without following or replacing an existing entry."""
    entry = stat_at(parent_fd, name)
    if entry is not None:
        if not stat.S_ISREG(entry.st_mode):
            raise UnsafePathError(f"unsafe regular file: {name}")
        existing_fd = open_regular_at(parent_fd, name)
        assert existing_fd is not None
        os.close(existing_fd)
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, mode, dir_fd=parent_fd)
    except FileExistsError as exc:
        raise UnsafePathError(f"unsafe regular file: {name}") from exc
    try:
        _write_all(descriptor, content)
    except Exception:
        os.close(descriptor)
        try:
            os.unlink(name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        raise
    os.close(descriptor)
    return True


def atomic_replace_at(parent_fd: int, name: str, content: bytes, *, mode: int = 0o644) -> None:
    """Atomically replace one child using only operations anchored to parent_fd."""
    _validate_component(name)
    temp_name = f".solomon-{os.getpid()}-{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temp_name, flags, mode, dir_fd=parent_fd)
    try:
        _write_all(descriptor, content)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temp_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def unlink_at(parent_fd: int, name: str) -> None:
    """Unlink one validated child name relative to parent_fd."""
    _validate_component(name)
    os.unlink(name, dir_fd=parent_fd)
