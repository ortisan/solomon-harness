"""Shared pytest fixtures for deterministic, fast repository tests."""

from __future__ import annotations

import os
import threading

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


def close_surreal_quietly(raw: object, timeout: float = 5.0) -> None:
    """Close a live SurrealDB connection without ever blocking the caller.

    The synchronous SurrealDB/websockets close handshake has been observed to
    stall indefinitely in CI. Skipping ``close()`` entirely avoids that stall
    but instead leaks the connection's keepalive/recv background threads for
    the rest of the pytest process; under a resource-constrained CI runner,
    enough leaked live connections accumulate to starve unrelated later
    tests. Running ``close()`` on a daemon thread and bounding the wait
    reclaims the connection in the common (fast) case while guaranteeing this
    call itself returns within ``timeout`` regardless of SDK behavior.
    """

    def _close() -> None:
        try:
            raw.close()  # type: ignore[attr-defined]
        except Exception:
            pass

    closer = threading.Thread(target=_close, daemon=True)
    closer.start()
    closer.join(timeout)
