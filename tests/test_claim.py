import unittest
from unittest.mock import patch
import datetime
import os
import shutil
import tempfile
import subprocess
import json
from io import StringIO

from solomon_harness import claim

class TestClaimLiveness(unittest.TestCase):
    def test_parse_claim_commit_message(self):
        msg = '{"session_id": "session-123", "acquired_at": "2026-07-06T00:00:00Z", "heartbeat_at": "2026-07-06T00:10:00Z"}'
        parsed = claim.parse_claim_commit_message(msg)
        self.assertEqual(parsed["session_id"], "session-123")
        self.assertEqual(parsed["acquired_at"], "2026-07-06T00:00:00Z")
        self.assertEqual(parsed["heartbeat_at"], "2026-07-06T00:10:00Z")

    def test_parse_invalid_claim_returns_none(self):
        self.assertIsNone(claim.parse_claim_commit_message("invalid json"))
        self.assertIsNone(claim.parse_claim_commit_message(""))

    def test_is_claim_active_within_ttl(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        self.assertTrue(claim.is_claim_active(claim_data, current_session_id="session-456", now=now))

    def test_is_claim_inactive_past_ttl_without_pr(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:50:00Z")
        self.assertFalse(claim.is_claim_active(claim_data, current_session_id="session-456", now=now, has_open_pr=False))

    def test_is_claim_active_past_ttl_with_active_pr(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:50:00Z")
        self.assertTrue(claim.is_claim_active(claim_data, current_session_id="session-456", now=now, has_open_pr=True))

    def test_same_session_is_not_active_blocking(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        self.assertFalse(claim.is_claim_active(claim_data, current_session_id="session-123", now=now))

    # -- M9: TTL lower bound ------------------------------------------------

    def test_is_claim_inactive_with_future_heartbeat_clock_skew(self):
        # A future heartbeat_at (clock skew, or a crafted ref) must never read
        # as fresh forever -- a negative elapsed is treated as malformed/expired.
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:30:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        self.assertFalse(claim.is_claim_active(claim_data, current_session_id="session-456", now=now))

    def test_is_claim_active_with_normal_past_heartbeat_within_ttl(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:05:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:10:00Z")
        self.assertTrue(claim.is_claim_active(claim_data, current_session_id="session-456", now=now))

    # -- M10: malformed claim ref cannot crash start -------------------------

    def test_parse_claim_commit_message_rejects_non_string_session_id(self):
        msg = json.dumps({"session_id": 12345, "heartbeat_at": "2026-07-06T00:00:00Z"})
        self.assertIsNone(claim.parse_claim_commit_message(msg))

    def test_parse_claim_commit_message_rejects_non_string_heartbeat_at(self):
        msg = json.dumps({"session_id": "sess-1", "heartbeat_at": 12345})
        self.assertIsNone(claim.parse_claim_commit_message(msg))

    def test_parse_claim_commit_message_rejects_non_string_acquired_at(self):
        msg = json.dumps({"session_id": "sess-1", "acquired_at": ["not", "a", "string"]})
        self.assertIsNone(claim.parse_claim_commit_message(msg))

    def test_parse_claim_commit_message_accepts_well_formed_claim(self):
        msg = json.dumps({
            "session_id": "sess-1",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        })
        parsed = claim.parse_claim_commit_message(msg)
        self.assertEqual(parsed["session_id"], "sess-1")

    def test_is_claim_active_survives_hostile_claim_data(self):
        # A crafted/corrupted claim dict with a non-string heartbeat_at must
        # never crash the `start` gate: is_claim_active must broaden its
        # except to catch the AttributeError from .replace() on a non-string
        # and degrade to "not active" instead of raising.
        claim_data = {"session_id": "session-123", "heartbeat_at": 12345}
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        self.assertFalse(
            claim.is_claim_active(claim_data, current_session_id="session-456", now=now)
        )


class TestSessionIdEntropy(unittest.TestCase):
    """M8: the no-env default session id must carry entropy (not just
    host:pid) so two independent no-env processes never collide as the "same
    session", while staying stable across repeated calls within one process."""

    def setUp(self):
        cache_patcher = patch.object(claim, "_SESSION_ID_CACHE", None)
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)
        self._env_patcher = patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        os.environ.pop("SOLOMON_SESSION_ID", None)
        os.environ.pop("CLAUDE_SESSION_ID", None)

    def test_default_session_id_is_stable_within_a_process(self):
        first = claim.get_current_session_id()
        second = claim.get_current_session_id()
        self.assertEqual(first, second)

    def test_default_session_id_contains_entropy_beyond_host_and_pid(self):
        session_id = claim.get_current_session_id()
        host = os.uname().nodename if hasattr(os, "uname") else None
        pid = os.getpid()
        # Never bare "host:pid" -- that collides across independent no-env
        # processes sharing a host and (after pid reuse) a pid.
        self.assertNotEqual(session_id, f"{host}:{pid}")
        parts = session_id.split(":")
        self.assertEqual(len(parts), 3, f"expected host:pid:entropy, got {session_id!r}")
        self.assertEqual(str(pid), parts[1])
        self.assertTrue(len(parts[2]) > 0)

    def test_env_session_id_takes_precedence_and_is_not_cached(self):
        os.environ["SOLOMON_SESSION_ID"] = "explicit-session"
        self.assertEqual(claim.get_current_session_id(), "explicit-session")


def _git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    )

class TestClaimGitOperations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin = os.path.join(self.tmp, "origin.git")
        self.local = os.path.join(self.tmp, "local")
        
        # Init bare origin
        _git(None, "init", "--bare", "-q", self.origin)
        
        # Init local clone
        _git(None, "clone", "-q", self.origin, self.local)
        _git(self.local, "config", "user.email", "t@example.com")
        _git(self.local, "config", "user.name", "Test")
        
        # Create initial commit to establish main
        with open(os.path.join(self.local, "README.md"), "w") as f:
            f.write("test")
        _git(self.local, "add", "README.md")
        _git(self.local, "commit", "-q", "-m", "initial commit")
        _git(self.local, "push", "-q", "origin", "HEAD:refs/heads/main")

        # Isolate from GitHub: the CAS pushes go to the temp bare origin above, but
        # claim_issue/release_claim also consult has_active_pr_or_review and edit the
        # issue assignee via gh -- those must never reach the real repo in a test.
        for target, kwargs in (
            ("solomon_harness.claim.has_active_pr_or_review", {"return_value": False}),
            ("solomon_harness.github._gh", {"return_value": {"ok": True, "stdout": ""}}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_claim_unclaimed_issue_succeeds(self):
        # Claim issue 99
        ok = claim.claim_issue(self.local, 99, current_session_id="sess-abc")
        self.assertTrue(ok)
        
        # Verify ref is created on origin
        ref_exists = False
        try:
            res = _git(self.local, "ls-remote", "origin", "refs/claims/issue-99")
            if "refs/claims/issue-99" in res.stdout:
                ref_exists = True
        except Exception:
            pass
        self.assertTrue(ref_exists)
        
        # Fetch and check claim contents
        c = claim.get_claim(self.local, 99)
        self.assertIsNotNone(c)
        self.assertEqual(c["session_id"], "sess-abc")

    def test_claim_already_claimed_fails(self):
        # Claim by A
        ok_a = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok_a)
        
        # Claim by B should fail because A's claim is active
        ok_b = claim.claim_issue(self.local, 99, current_session_id="sess-b")
        self.assertFalse(ok_b)

    def test_reclaim_stale_claim_succeeds(self):
        # Claim by A (old time)
        past_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)).isoformat()
        # Mock git commit creation or directly create a claim commit on origin
        # Wait, let's create a stale claim using custom time
        claim_data = {
            "session_id": "sess-a",
            "acquired_at": past_time,
            "heartbeat_at": past_time,
        }
        # Push it directly
        tree_sha = _git(self.local, "write-tree").stdout.strip()
        commit_sha = _git(self.local, "commit-tree", "-m", json.dumps(claim_data), tree_sha).stdout.strip()
        _git(self.local, "push", "-q", "origin", f"{commit_sha}:refs/claims/issue-99")
        
        # Now B attempts to claim; since it is stale (40 mins old) and has no open PR, it should succeed!
        ok_b = claim.claim_issue(self.local, 99, current_session_id="sess-b")
        self.assertTrue(ok_b)
        
        c = claim.get_claim(self.local, 99)
        self.assertEqual(c["session_id"], "sess-b")

    def test_release_claim_removes_ref(self):
        # Claim by A
        claim.claim_issue(self.local, 99, current_session_id="sess-a")

        # Release by A
        ok = claim.release_claim(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

        # Check ref is gone
        res = _git(self.local, "ls-remote", "origin", "refs/claims/issue-99")
        self.assertNotIn("refs/claims/issue-99", res.stdout)

    # -- B5b: fail-closed reclaim --------------------------------------------

    def test_reclaim_blocked_when_pr_liveness_check_errors(self):
        # A stale (past-TTL) claim by sess-a exists. If gh cannot be reached
        # to confirm the issue is genuinely unprotected (a transient failure,
        # not a clean "no PR"), the reclaim must fail closed: the existing
        # claim is treated as still active rather than stolen.
        past_time = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        claim_data = {
            "session_id": "sess-a",
            "acquired_at": past_time,
            "heartbeat_at": past_time,
        }
        tree_sha = _git(self.local, "write-tree").stdout.strip()
        commit_sha = _git(
            self.local, "commit-tree", "-m", json.dumps(claim_data), tree_sha
        ).stdout.strip()
        _git(self.local, "push", "-q", "origin", f"{commit_sha}:refs/claims/issue-99")

        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": False, "error": "transient gh failure"},
        ):
            ok_b = claim.claim_issue(self.local, 99, current_session_id="sess-b")
        self.assertFalse(ok_b)

        c = claim.get_claim(self.local, 99)
        self.assertEqual(c["session_id"], "sess-a")

    def test_fresh_claim_on_unclaimed_issue_proceeds_even_when_gh_errors(self):
        # No ref exists at all: there is nothing to protect, so a gh failure
        # (which only matters for deciding whether to steal an EXISTING
        # claim) must never block a fresh claim.
        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": False, "error": "transient gh failure"},
        ):
            ok = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

    def test_same_session_reentry_proceeds_even_when_gh_errors(self):
        # Re-entry by the SAME session that already holds the claim must not
        # be blocked by liveness uncertainty -- it never needed liveness to
        # decide anything (is_claim_active already special-cases same-session).
        ok_a = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok_a)

        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": False, "error": "transient gh failure"},
        ):
            ok_again = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok_again)

    # -- B5a: heartbeat writer ------------------------------------------------

    def test_refresh_claim_updates_heartbeat_at(self):
        claim.claim_issue(self.local, 99, current_session_id="sess-a")
        original = claim.get_claim(self.local, 99)

        ok = claim.refresh_claim(self.local, 99, "sess-a")
        self.assertTrue(ok)

        refreshed = claim.get_claim(self.local, 99)
        self.assertEqual(refreshed["session_id"], "sess-a")
        self.assertGreaterEqual(
            datetime.datetime.fromisoformat(refreshed["heartbeat_at"]),
            datetime.datetime.fromisoformat(original["heartbeat_at"]),
        )

    def test_refresh_claim_returns_false_when_no_longer_owned_by_session(self):
        # sess-a's claim goes stale, sess-b takes it over. sess-a's heartbeat
        # thread must lose gracefully (return False, not raise) instead of
        # clobbering sess-b's claim.
        past_time = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        claim_data = {
            "session_id": "sess-a",
            "acquired_at": past_time,
            "heartbeat_at": past_time,
        }
        tree_sha = _git(self.local, "write-tree").stdout.strip()
        commit_sha = _git(
            self.local, "commit-tree", "-m", json.dumps(claim_data), tree_sha
        ).stdout.strip()
        _git(self.local, "push", "-q", "origin", f"{commit_sha}:refs/claims/issue-99")

        ok_b = claim.claim_issue(self.local, 99, current_session_id="sess-b")
        self.assertTrue(ok_b)

        ok_refresh = claim.refresh_claim(self.local, 99, "sess-a")
        self.assertFalse(ok_refresh)

        c = claim.get_claim(self.local, 99)
        self.assertEqual(c["session_id"], "sess-b")

    def test_refresh_claim_returns_false_when_ref_missing(self):
        self.assertFalse(claim.refresh_claim(self.local, 99, "sess-a"))

    @patch("solomon_harness.claim.claim_issue")
    @patch("solomon_harness.claim.get_claim")
    @patch("solomon_harness.workflows._read_command_file")
    def test_run_stage_start_spawns_and_stops_claim_heartbeat_thread(
        self, mock_read, mock_get, mock_claim_issue
    ):
        from solomon_harness import workflows

        mock_read.return_value = "---\nallowed-tools: Bash\n---\nDo work on $ARGUMENTS"
        mock_get.return_value = None
        mock_claim_issue.return_value = True

        class _Proc:
            returncode = 0

        with (
            patch("subprocess.run", return_value=_Proc()),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread = mock_thread_cls.return_value
            rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")

        self.assertEqual(rc, 0)
        mock_thread_cls.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        self.assertTrue(kwargs.get("daemon"))
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once()

    # -- Best-effort SurrealDB claim mirror ------------------------------------

    def test_claim_issue_writes_best_effort_mirror(self):
        ok = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

        holder = claim.get_claim_holder(self.local, 99)
        self.assertIsNotNone(holder)
        self.assertEqual(holder["session_id"], "sess-a")

    def test_release_claim_clears_mirror(self):
        claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertIsNotNone(claim.get_claim_holder(self.local, 99))

        ok = claim.release_claim(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

        self.assertIsNone(claim.get_claim_holder(self.local, 99))

    def test_mirror_write_failure_does_not_affect_claim_result(self):
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            side_effect=RuntimeError("memory layer down"),
        ):
            ok = claim.claim_issue(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

        # The git ref is still the real source of truth, unaffected.
        c = claim.get_claim(self.local, 99)
        self.assertEqual(c["session_id"], "sess-a")

    def test_mirror_clear_failure_does_not_affect_release_result(self):
        claim.claim_issue(self.local, 99, current_session_id="sess-a")

        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            side_effect=RuntimeError("memory layer down"),
        ):
            ok = claim.release_claim(self.local, 99, current_session_id="sess-a")
        self.assertTrue(ok)

    # -- Claim-aware direct scan path -----------------------------------------

    def test_filter_unclaimed_excludes_actively_claimed_issue(self):
        claim.claim_issue(self.local, 99, current_session_id="other-sess")

        result = claim.filter_unclaimed(self.local, [99, 100], current_session_id="sess-b")
        self.assertNotIn(99, result)
        self.assertIn(100, result)

    def test_filter_unclaimed_degrades_to_unfiltered_when_claims_fetch_fails(self):
        with patch(
            "solomon_harness.claim.fetch_all_claims",
            side_effect=RuntimeError("git unavailable"),
        ):
            result = claim.filter_unclaimed(self.local, [1, 2, 3], current_session_id="sess-b")
        self.assertEqual(result, [1, 2, 3])

    @patch("solomon_harness.claim.get_claim")
    @patch("solomon_harness.claim.is_claim_active")
    @patch("solomon_harness.workflows._read_command_file")
    def test_run_stage_start_blocked_on_active_claim(self, mock_read, mock_active, mock_get):
        from solomon_harness import workflows
        mock_read.return_value = "---\nallowed-tools: Bash\n---\nbody"
        mock_get.return_value = {"session_id": "other-session", "acquired_at": "2026-07-06T00:00:00Z"}
        mock_active.return_value = True
        
        rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")
        self.assertEqual(rc, 1)

    @patch("solomon_harness.tools.database_client.DatabaseClient.get_open_issues")
    @patch("solomon_harness.claim.fetch_all_claims")
    @patch("solomon_harness.claim.is_claim_active")
    def test_memory_service_filters_claimed_issues(self, mock_active, mock_fetch, mock_db_issues):
        from solomon_harness.memory_service import MemoryService
        
        mock_db_issues.return_value = [
            {"github_id": "1", "title": "issue 1"},
            {"github_id": "2", "title": "issue 2"},
            {"github_id": "tracking-row", "title": "RAID row"},
        ]
        
        mock_fetch.return_value = {
            1: {"session_id": "other-sess"}
        }
        
        def side_effect(claim_data, current_session_id, **kw):
            return claim_data.get("session_id") == "other-sess"
        mock_active.side_effect = side_effect
        
        service = MemoryService(harness_dir=self.local)
        res = service.get_open_issues()
        issues = res["issues"]
        
        self.assertEqual(len(issues), 2)
        github_ids = [i["github_id"] for i in issues]
        self.assertNotIn("1", github_ids)
        self.assertIn("2", github_ids)
        self.assertIn("tracking-row", github_ids)

    @patch("solomon_harness.tools.database_client.DatabaseClient.get_open_issues")
    @patch("solomon_harness.claim.fetch_all_claims")
    def test_memory_service_degrades_and_logs_on_claim_filter_failure(
        self, mock_fetch, mock_db_issues
    ):
        # Item 8: no silent `except Exception: pass` on this safety path -- a
        # claim-lookup failure must degrade to the unfiltered list AND log,
        # not swallow.
        from solomon_harness.memory_service import MemoryService

        mock_db_issues.return_value = [{"github_id": "1", "title": "issue 1"}]
        mock_fetch.side_effect = RuntimeError("git unavailable")

        service = MemoryService(harness_dir=self.local)
        with self.assertLogs("solomon_harness.memory_service", level="WARNING") as logs:
            res = service.get_open_issues()

        self.assertEqual(len(res["issues"]), 1)
        self.assertTrue(any("degraded" in m.lower() for m in logs.output))

    @patch("sys.stdout", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.get_claim")
    def test_cli_claim_status_unclaimed(self, mock_get, mock_stdout):
        from solomon_harness.cli import main
        mock_get.return_value = None
        
        main(harness_dir=self.local, argv=["claim", "status", "99"])
        self.assertIn("Issue #99 is unclaimed.", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.release_claim")
    def test_cli_claim_release(self, mock_release, mock_stdout):
        from solomon_harness.cli import main
        mock_release.return_value = True
        
        main(harness_dir=self.local, argv=["claim", "release", "99"])
        mock_release.assert_called_once_with(self.local, 99, current_session_id=unittest.mock.ANY)
        self.assertIn("Released claim on issue #99.", mock_stdout.getvalue())

if __name__ == '__main__':
    from io import StringIO
    unittest.main()
