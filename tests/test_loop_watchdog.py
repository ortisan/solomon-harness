import threading
import time
import unittest

from solomon_harness import loop_watchdog


class FakeProc:
    def __init__(self, run_seconds=None):
        self._run_seconds = run_seconds
        self._start = time.time()
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._lock = threading.Lock()

    def poll(self):
        if self.terminated or self.killed:
            return self.returncode
        if self._run_seconds is not None and time.time() - self._start >= self._run_seconds:
            with self._lock:
                self.returncode = 0
            return 0
        return None

    def terminate(self):
        with self._lock:
            self.terminated = True
            if self.returncode is None:
                self.returncode = -15

    def kill(self):
        with self._lock:
            self.killed = True
            if self.returncode is None:
                self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class TestWatchdogConfig(unittest.TestCase):
    def test_defaults_are_nested_3m_6m_45m(self):
        cfg = loop_watchdog.WatchdogConfig.from_loop_block({})
        self.assertEqual(cfg.idle_timeout, 180.0)
        self.assertEqual(cfg.child_backstop, 360.0)
        self.assertEqual(cfg.terminal_cap, 2700.0)
        # The backstop must exceed idle so the fast watchdog heals first.
        self.assertGreater(cfg.child_backstop, cfg.idle_timeout)
        self.assertGreater(cfg.terminal_cap, cfg.child_backstop)

    def test_config_overrides_are_read_from_the_loop_block(self):
        cfg = loop_watchdog.WatchdogConfig.from_loop_block(
            {"stall_idle_seconds": 5, "stall_backstop_seconds": 10, "stall_terminal_seconds": 60}
        )
        self.assertEqual(cfg.idle_timeout, 5.0)
        self.assertEqual(cfg.child_backstop, 10.0)
        self.assertEqual(cfg.terminal_cap, 60.0)

    def test_invalid_values_fall_back_to_defaults(self):
        cfg = loop_watchdog.WatchdogConfig.from_loop_block({"stall_idle_seconds": "x"})
        self.assertEqual(cfg.idle_timeout, 180.0)


class TestStallMonitor(unittest.TestCase):
    def test_kills_on_idle_when_no_activity(self):
        proc = FakeProc()
        cfg = loop_watchdog.WatchdogConfig(idle_timeout=0.15, child_backstop=10, terminal_cap=10)
        mon = loop_watchdog.StallMonitor(proc, cfg, poll_interval=0.02)
        mon.start()
        deadline = time.time() + 2.0
        while not mon.stalled and time.time() < deadline:
            time.sleep(0.02)
        mon.stop()
        self.assertTrue(mon.stalled)
        self.assertIn("idle", mon.reason)
        self.assertTrue(proc.terminated or proc.killed)

    def test_activity_keeps_the_process_alive_then_terminal_cap_fires(self):
        proc = FakeProc()
        cfg = loop_watchdog.WatchdogConfig(idle_timeout=0.3, child_backstop=10, terminal_cap=0.4)
        mon = loop_watchdog.StallMonitor(proc, cfg, poll_interval=0.02)
        mon.start()
        # Keep marking activity so idle never fires; the terminal cap must win.
        end = time.time() + 0.6
        while time.time() < end and not mon.stalled:
            mon.mark_activity()
            time.sleep(0.05)
        deadline = time.time() + 1.0
        while not mon.stalled and time.time() < deadline:
            time.sleep(0.02)
        mon.stop()
        self.assertTrue(mon.stalled)
        self.assertIn("terminal", mon.reason)

    def test_healthy_process_that_exits_is_not_stalled(self):
        proc = FakeProc(run_seconds=0.1)
        cfg = loop_watchdog.WatchdogConfig(idle_timeout=5, child_backstop=10, terminal_cap=10)
        mon = loop_watchdog.StallMonitor(proc, cfg, poll_interval=0.02)
        mon.start()
        deadline = time.time() + 2.0
        while proc.poll() is None and time.time() < deadline:
            mon.mark_activity()
            time.sleep(0.02)
        mon.stop()
        self.assertFalse(mon.stalled)
        self.assertFalse(proc.killed)


if __name__ == "__main__":
    unittest.main()
