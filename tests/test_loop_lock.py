"""Tests for the single-driver loop lock (Phase 0 safety floor).

The lock anchors at the git *common* directory so every linked worktree of a
repository contends on one lockfile, which is the precondition for fixing the
recorded concurrent-driver race (premature merges bypassing the review gate).
"""

import os
import tempfile
import unittest

from solomon_harness import loop_lock
from solomon_harness.loop_lock import LoopLock, LoopLockHeld


class TestResolveLockPath(unittest.TestCase):
    def test_non_git_dir_falls_back_to_dot_solomon(self):
        root = tempfile.mkdtemp()
        path = loop_lock.resolve_lock_path(root)
        self.assertEqual(path, os.path.join(os.path.abspath(root), ".solomon", "loop.lock"))

    def test_git_directory_anchors_in_common_dir(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".git"))
        path = loop_lock.resolve_lock_path(root)
        self.assertEqual(path, os.path.join(root, ".git", "solomon-loop.lock"))

    def test_linked_worktree_anchors_in_main_common_dir(self):
        tmp = tempfile.mkdtemp()
        main = os.path.join(tmp, "main")
        os.makedirs(os.path.join(main, ".git", "worktrees", "wt"))
        wt = os.path.join(tmp, "wt")
        os.makedirs(wt)
        gitdir = os.path.join(main, ".git", "worktrees", "wt")
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as f:
            f.write(f"gitdir: {gitdir}\n")
        # The worktree must resolve to the SAME lock the main checkout uses.
        self.assertEqual(
            loop_lock.resolve_lock_path(wt),
            os.path.join(main, ".git", "solomon-loop.lock"),
        )
        self.assertEqual(
            loop_lock.resolve_lock_path(main),
            os.path.join(main, ".git", "solomon-loop.lock"),
        )


class TestLoopLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "loop.lock")

    def _lock(self, session_id, **kw):
        kw.setdefault("host", "h1")
        kw.setdefault("clock", lambda: 1000.0)
        kw.setdefault("ttl", 1800.0)
        return LoopLock(lock_path=self.path, session_id=session_id, **kw)

    def test_exclusive_acquire_blocks_a_second_session(self):
        self._lock("a").acquire()
        with self.assertRaises(LoopLockHeld) as ctx:
            self._lock("b").acquire()
        self.assertEqual(ctx.exception.holder["session_id"], "a")

    def test_reentrant_same_session_does_not_raise(self):
        a = self._lock("a")
        a.acquire()
        a.acquire()  # same session re-entrancy must be allowed
        self.assertEqual(a.read()["session_id"], "a")

    def test_release_removes_own_lock(self):
        a = self._lock("a")
        a.acquire()
        a.release()
        self.assertIsNone(a.read())
        self.assertFalse(os.path.exists(self.path))

    def test_release_keeps_a_live_foreign_lock(self):
        self._lock("a", pid=os.getpid()).acquire()
        # b never owned it; releasing must not delete a live foreign lock.
        self._lock("b").release()
        self.assertEqual(self._lock("z").read()["session_id"], "a")

    def test_cross_host_stale_by_ttl_is_reclaimed(self):
        # TTL only governs a cross-host holder (no remote pid to probe).
        self._lock("old", host="other-host", clock=lambda: 1000.0).acquire()
        new = self._lock("new", host="h1", clock=lambda: 1000.0 + 5000.0)  # past TTL
        new.acquire()
        self.assertEqual(new.read()["session_id"], "new")

    def test_same_host_live_pid_is_never_stale_past_ttl(self):
        # Regression: a live same-host holder must NOT be reclaimed on the TTL,
        # even far past it (a long stage never refreshes its heartbeat).
        self._lock("holder", pid=os.getpid(), clock=lambda: 1000.0).acquire()
        new = self._lock(
            "new", host="h1", pid=os.getpid(), pid_alive=lambda p: True,
            clock=lambda: 1000.0 + 999999.0,
        )
        with self.assertRaises(LoopLockHeld):
            new.acquire()

    def test_stale_by_dead_pid_is_reclaimed(self):
        self._lock("holder", pid=424242).acquire()
        new = self._lock("new", pid=os.getpid(), pid_alive=lambda pid: False)
        new.acquire()
        self.assertEqual(new.read()["session_id"], "new")

    def test_live_foreign_pid_blocks(self):
        self._lock("holder", pid=424242).acquire()
        with self.assertRaises(LoopLockHeld):
            self._lock("new", pid=os.getpid(), pid_alive=lambda pid: True).acquire()

    def test_pid_reuse_is_detected_as_stale(self):
        # Regression: the original holder (pid 424242) crashed and the OS
        # recycled its pid for an unrelated process. A bare os.kill(pid, 0)
        # liveness check alone cannot tell the two apart -- it reports the pid
        # as alive forever. The recorded process-start-time must disambiguate:
        # same pid, but a different start time than what was recorded at
        # acquire time means the live process is NOT the original holder.
        self._lock(
            "holder", pid=424242,
            pid_start_time=lambda pid: "Mon Jan  1 00:00:00 2026",
        ).acquire()
        new = self._lock(
            "new", pid=os.getpid(),
            pid_alive=lambda pid: True,  # the recycled pid looks alive
            pid_start_time=lambda pid: "Tue Jan  2 00:00:00 2026",  # different process
        )
        new.acquire()
        self.assertEqual(new.read()["session_id"], "new")

    def test_pid_not_reused_with_same_start_time_stays_live(self):
        # Same pid, same recorded start time: the original holder is still
        # running, so the lock must stay held and refuse the second driver.
        self._lock(
            "holder", pid=424242,
            pid_start_time=lambda pid: "Mon Jan  1 00:00:00 2026",
        ).acquire()
        new = self._lock(
            "new", pid=os.getpid(),
            pid_alive=lambda pid: True,
            pid_start_time=lambda pid: "Mon Jan  1 00:00:00 2026",
        )
        with self.assertRaises(LoopLockHeld):
            new.acquire()

    def test_held_by_other(self):
        self.assertIsNone(self._lock("a").held_by_other())
        self._lock("a", pid=os.getpid()).acquire()
        holder = self._lock("b").held_by_other()
        self.assertEqual(holder["session_id"], "a")

    def test_context_manager_acquires_and_releases(self):
        with self._lock("a"):
            self.assertEqual(self._lock("z").read()["session_id"], "a")
        self.assertFalse(os.path.exists(self.path))

    def test_reentrant_acquire_does_not_release_the_outer_holders_lock(self):
        # #197: a nested `dev <stage>` call resolves the SAME session_id
        # as its still-running parent (propagated via SOLOMON_SESSION_ID) and
        # lands on the reentrant branch above -- but it must not tear down the
        # lock on its own way out. Only the call that ORIGINALLY created (or
        # reclaimed) the lockfile owns its lifecycle; a reentrant holder
        # releasing it would free the lock while the outer driver is still
        # mid-run, reopening the exact concurrent-driver race the lock exists
        # to close.
        outer = self._lock("a")
        outer.acquire()
        inner = self._lock("a")  # separate instance, same session_id: nested call
        inner.acquire()
        inner.release()
        held = outer.read()
        self.assertIsNotNone(held, "the outer holder's lock must survive a nested release")
        self.assertEqual(held["session_id"], "a")
        # The true owner can still release it when it actually finishes.
        outer.release()
        self.assertIsNone(outer.read())

    def test_reclaim_cas_loser_backs_off(self):
        # Two drivers race to reclaim the same dead lock. After our atomic write,
        # the confirmation re-read sees a live foreign winner, so we must back off
        # (raise LoopLockHeld) rather than both believing we hold it.
        self._lock("pre", host="other-host", clock=lambda: 0.0).acquire()  # file exists -> reclaim path
        new = self._lock("loser", host="h1", pid=os.getpid(), clock=lambda: 1.0e9)
        seq = [
            {"session_id": "dead", "host": "other-host", "pid": 1, "heartbeat_at": loop_lock._iso(0.0)},
            {"session_id": "winner", "host": "h1", "pid": os.getpid(), "heartbeat_at": loop_lock._iso(1.0e9)},
        ]
        new.read = lambda: seq.pop(0)
        with self.assertRaises(LoopLockHeld) as ctx:
            new.acquire()
        self.assertEqual(ctx.exception.holder["session_id"], "winner")


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "loop.lock")

    def test_is_push_or_merge(self):
        self.assertTrue(loop_lock.is_push_or_merge("git push origin main"))
        self.assertTrue(loop_lock.is_push_or_merge("gh pr merge 28 --squash"))
        self.assertTrue(loop_lock.is_push_or_merge("cd x && git merge develop"))
        self.assertFalse(loop_lock.is_push_or_merge("git status"))
        self.assertFalse(loop_lock.is_push_or_merge("git fetch --all"))

    def test_guard_allows_non_push_commands(self):
        LoopLock(lock_path=self.path, session_id="foreign", pid=os.getpid()).acquire()
        lock = LoopLock(lock_path=self.path, session_id="me")
        block, _ = loop_lock.guard_verdict(
            {"tool_name": "Bash", "tool_input": {"command": "git status"}}, lock
        )
        self.assertFalse(block)

    def test_guard_allows_push_when_no_foreign_lock(self):
        lock = LoopLock(lock_path=self.path, session_id="me")
        block, _ = loop_lock.guard_verdict(
            {"tool_name": "Bash", "tool_input": {"command": "git push"}}, lock
        )
        self.assertFalse(block)

    def test_guard_blocks_push_under_live_foreign_lock(self):
        LoopLock(lock_path=self.path, session_id="foreign", pid=os.getpid()).acquire()
        lock = LoopLock(lock_path=self.path, session_id="me")
        block, reason = loop_lock.guard_verdict(
            {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 28"}}, lock
        )
        self.assertTrue(block)
        self.assertIn("single-driver lock", reason)

    def test_guard_ignores_non_bash_tools(self):
        LoopLock(lock_path=self.path, session_id="foreign", pid=os.getpid()).acquire()
        lock = LoopLock(lock_path=self.path, session_id="me")
        block, _ = loop_lock.guard_verdict({"tool_name": "Edit"}, lock)
        self.assertFalse(block)


if __name__ == "__main__":
    unittest.main()
