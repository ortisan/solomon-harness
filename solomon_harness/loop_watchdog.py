"""Nested stall watchdog for the headless engine subprocess (#341 package 2).

A headless `/solomon-*` run that wedges holds the single-driver lock forever,
because ``LoopLock.is_stale`` treats a live same-host process as never stale.
This watchdog bounds a run by three nested time budgets — a fast per-attempt
idle timeout, a child backstop that must exceed idle so the fast watchdog heals
first, and an absolute terminal cap — and kills the process when any is
exceeded, so the lock is always released.
"""

import threading
import time
from typing import Any, Optional

DEFAULT_IDLE_TIMEOUT = 180.0
DEFAULT_CHILD_BACKSTOP = 360.0
DEFAULT_TERMINAL_CAP = 2700.0


def _positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


class WatchdogConfig:
    """The three nested stall budgets, in seconds."""

    def __init__(
        self,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        child_backstop: float = DEFAULT_CHILD_BACKSTOP,
        terminal_cap: float = DEFAULT_TERMINAL_CAP,
    ) -> None:
        self.idle_timeout = idle_timeout
        self.child_backstop = child_backstop
        self.terminal_cap = terminal_cap

    @classmethod
    def from_loop_block(cls, block: Optional[dict]) -> "WatchdogConfig":
        block = block or {}
        return cls(
            idle_timeout=_positive_float(block.get("stall_idle_seconds"), DEFAULT_IDLE_TIMEOUT),
            child_backstop=_positive_float(block.get("stall_backstop_seconds"), DEFAULT_CHILD_BACKSTOP),
            terminal_cap=_positive_float(block.get("stall_terminal_seconds"), DEFAULT_TERMINAL_CAP),
        )


class StallMonitor:
    """Watches one process and kills it when a stall budget is exceeded.

    ``mark_activity`` is called from the output-reading loop so the idle timer
    resets on every chunk; the terminal cap ignores activity and bounds total
    wall-clock. The kill escalates terminate then kill, and ``stalled``/``reason``
    record the verdict for the caller.
    """

    def __init__(self, proc: Any, config: WatchdogConfig, poll_interval: float = 1.0) -> None:
        self._proc = proc
        self._config = config
        self._poll_interval = poll_interval
        self._start = time.time()
        self._last_activity = self._start
        self._activity_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stalled = False
        self.reason = ""

    def mark_activity(self) -> None:
        with self._activity_lock:
            self._last_activity = time.time()

    def start(self) -> "StallMonitor":
        self._thread = threading.Thread(target=self._run, name="stall-watchdog", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._proc.poll() is not None:
                return
            now = time.time()
            with self._activity_lock:
                idle_for = now - self._last_activity
            elapsed = now - self._start
            reason = None
            if elapsed >= self._config.terminal_cap:
                reason = f"terminal cap {self._config.terminal_cap:.0f}s exceeded"
            elif idle_for >= self._config.idle_timeout:
                reason = f"idle {self._config.idle_timeout:.0f}s exceeded"
            if reason is not None:
                self.stalled = True
                self.reason = reason
                self._kill()
                return
            self._stop_event.wait(self._poll_interval)

    def _kill(self) -> None:
        try:
            self._proc.terminate()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=self._config.child_backstop - self._config.idle_timeout or 5.0)
        except Exception:
            pass
        if self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
