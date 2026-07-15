"""Shared pytest fixtures for deterministic, fast repository tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def bypass_physical_fsync(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid physical disk flushes except in tests that opt into durability I/O.

    Production continues to call :func:`os.fsync`; this fixture replaces only
    that physical syscall while pytest executes. Tests marked ``real_fsync``
    retain the operating-system implementation.
    """

    if request.node.get_closest_marker("real_fsync") is not None:
        return

    monkeypatch.setattr(os, "fsync", lambda _descriptor: None)
