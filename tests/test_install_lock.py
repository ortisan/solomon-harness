from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from solomon_harness.install_lock import install_operation_lock, operation_lock_path


@pytest.mark.integration
def test_install_operation_lock_serializes_independent_processes(tmp_path: Path) -> None:
    held = tmp_path / "child-held"
    release = tmp_path / "release-child"
    script = """
import sys
import time
from pathlib import Path
from solomon_harness.install_lock import install_operation_lock

root, held, release = map(Path, sys.argv[1:])
with install_operation_lock(root):
    held.write_text("held", encoding="utf-8")
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("parent never released child lock")
        time.sleep(0.01)
"""
    child = subprocess.Popen(  # noqa: S603 - fixed interpreter and inline test program
        [sys.executable, "-c", script, str(tmp_path), str(held), str(release)]
    )
    try:
        deadline = time.monotonic() + 10
        while not held.exists():
            if child.poll() is not None:
                raise AssertionError(f"lock holder exited early with {child.returncode}")
            if time.monotonic() >= deadline:
                raise AssertionError("lock holder did not acquire within ten seconds")
            time.sleep(0.01)

        acquired = threading.Event()

        def contend() -> None:
            with install_operation_lock(tmp_path):
                acquired.set()

        contender = threading.Thread(target=contend, daemon=True)
        contender.start()
        assert not acquired.wait(0.1)
        release.write_text("release", encoding="utf-8")
        assert acquired.wait(5)
        contender.join(timeout=5)
        assert not contender.is_alive()
    finally:
        release.touch()
        child.wait(timeout=10)


@pytest.mark.unit
def test_install_operation_lock_is_reentrant_and_private(tmp_path: Path) -> None:
    expected = tmp_path / ".agents" / "solomon" / "state" / "install.lock"

    with install_operation_lock(tmp_path):
        with install_operation_lock(tmp_path):
            assert operation_lock_path(tmp_path) == expected
            assert expected.is_file()

    if os.name != "nt":
        assert expected.stat().st_mode & 0o777 == 0o600
        assert expected.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.unit
def test_install_operation_lock_rejects_symlinked_state(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    state = tmp_path / ".agents" / "solomon" / "state"
    state.parent.mkdir(parents=True)
    state.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        with install_operation_lock(tmp_path):
            raise AssertionError("unreachable")


@pytest.mark.unit
def test_install_operation_lock_rejects_symlinked_lock_file(tmp_path: Path) -> None:
    outside = tmp_path / "outside-lock"
    outside.write_text("outside\n", encoding="utf-8")
    lock_path = operation_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True)
    lock_path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink|regular file"):
        with install_operation_lock(tmp_path):
            raise AssertionError("unreachable")

    assert outside.read_text(encoding="utf-8") == "outside\n"


@pytest.mark.integration
def test_three_contenders_remain_serialized_when_canonical_inode_is_removed(
    tmp_path: Path,
) -> None:
    start = threading.Barrier(3)
    counter_lock = threading.Lock()
    first = threading.Event()
    active = 0
    maximum = 0
    errors: list[BaseException] = []

    def contend() -> None:
        nonlocal active, maximum
        try:
            start.wait(timeout=5)
            with install_operation_lock(tmp_path):
                with counter_lock:
                    active += 1
                    maximum = max(maximum, active)
                if not first.is_set():
                    first.set()
                    operation_lock_path(tmp_path).unlink()
                time.sleep(0.03)
                with counter_lock:
                    active -= 1
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    contenders = [threading.Thread(target=contend) for _ in range(3)]
    for contender in contenders:
        contender.start()
    for contender in contenders:
        contender.join(timeout=10)

    assert not errors
    assert all(not contender.is_alive() for contender in contenders)
    assert maximum == 1
