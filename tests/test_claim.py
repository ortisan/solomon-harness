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

    def test_loop_lock_and_claim_share_one_session_identity(self):
        # Regression: LoopLock's default session_id and claim's must resolve to
        # the SAME value in one process. If they diverge (the lock on host:pid,
        # the claim on host:pid:entropy), a nested claim-gated `dev start` tags
        # its claim with one id while the lock holds another and self-deadlocks
        # on its own claim.
        from solomon_harness.loop_lock import LoopLock
        stripped = {
            k: v for k, v in os.environ.items()
            if k not in ("SOLOMON_SESSION_ID", "CLAUDE_SESSION_ID")
        }
        with patch.dict(os.environ, stripped, clear=True):
            lock = LoopLock(lock_path="/tmp/solomon-session-id-regression.lock")
            self.assertEqual(lock.session_id, claim.get_current_session_id())
            self.assertEqual(lock.session_id.count(":"), 2)

    def test_claim_category_is_non_semantic(self):
        # Regression: claim mirror writes (one per heartbeat tick) must NOT be
        # embedded into the HNSW semantic index or they drown real notes.
        from solomon_harness.tools.database_client import is_semantic_category
        self.assertFalse(is_semantic_category("claim"))

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

    def test_refresh_claim_keeps_trying_when_ref_temporarily_missing(self):
        # A missing/unfetchable ref is a transient condition, not a confirmed
        # takeover, so the heartbeat must keep trying (True), never stop: a
        # transient git/network blip must not let a lapsed heartbeat reopen the
        # #24 double-pick. A genuine takeover is caught on the next tick, when
        # the ref reads a foreign owner (that path returns False).
        self.assertTrue(claim.refresh_claim(self.local, 99, "sess-a"))

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

    @patch("solomon_harness.claim.claim_issue")
    @patch("solomon_harness.claim.get_claim_ref")
    @patch("solomon_harness.claim.is_claim_active")
    @patch("solomon_harness.claim.get_claim")
    @patch("solomon_harness.workflows._read_command_file")
    def test_run_stage_start_refuses_when_claim_issue_refuses_with_ref_present(
        self, mock_read, mock_get, mock_active, mock_get_ref, mock_claim_issue
    ):
        # BLOCKER regression: when claim_issue fails closed (an active claim, or
        # PR/review liveness it could not confirm), run_stage must refuse -- not
        # fall through to "proceeding without one" because a weaker TTL-only
        # recheck reads the stale claim as inactive. Any ref still present after
        # a refusal means: do not start. The recheck reads the REF (not the
        # parsed claim), so a malformed ref also refuses.
        from solomon_harness import workflows
        mock_read.return_value = "---\nallowed-tools: Bash\n---\nbody"
        mock_active.return_value = False  # pre-check must not block; we reach claim_issue
        mock_get.return_value = {"session_id": "other-session", "acquired_at": "2026-07-06T00:00:00Z"}
        mock_get_ref.return_value = ("sha1", {"session_id": "other-session", "acquired_at": "2026-07-06T00:00:00Z"})
        mock_claim_issue.return_value = False  # claim_issue fails closed
        rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")
        self.assertEqual(rc, 1)

    @patch("solomon_harness.claim.claim_issue")
    @patch("solomon_harness.claim.get_claim_ref")
    @patch("solomon_harness.claim.is_claim_active")
    @patch("solomon_harness.claim.get_claim")
    @patch("solomon_harness.workflows._read_command_file")
    def test_run_stage_start_refuses_on_malformed_ref_after_refusal(
        self, mock_read, mock_get, mock_active, mock_get_ref, mock_claim_issue
    ):
        # A ref whose content is malformed still means "a ref is present":
        # after a claim_issue refusal the stage must refuse, never proceed
        # claimless past a poisoned ref.
        from solomon_harness import workflows
        mock_read.return_value = "---\nallowed-tools: Bash\n---\nbody"
        mock_active.return_value = False
        mock_get.return_value = None
        mock_get_ref.return_value = ("sha1", None)
        mock_claim_issue.return_value = False
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
        # not swallow. Filtering now runs through claim.filter_unclaimed, which
        # catches the fetch failure and logs (on the claim logger) before
        # returning the unfiltered set, so the degrade is still observable.
        from solomon_harness.memory_service import MemoryService

        mock_db_issues.return_value = [{"github_id": "1", "title": "issue 1"}]
        mock_fetch.side_effect = RuntimeError("git unavailable")

        service = MemoryService(harness_dir=self.local)
        with self.assertLogs("solomon_harness.claim", level="WARNING") as logs:
            res = service.get_open_issues()

        self.assertEqual(len(res["issues"]), 1)
        self.assertTrue(any("unfiltered" in m.lower() for m in logs.output))

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
        mock_release.assert_called_once_with(
            self.local, 99, current_session_id=unittest.mock.ANY, force=False
        )
        self.assertIn("Released claim on issue #99.", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.release_claim")
    def test_cli_claim_release_force_flag_passes_through(self, mock_release, mock_stdout):
        from solomon_harness.cli import main
        mock_release.return_value = True

        main(harness_dir=self.local, argv=["claim", "release", "99", "--force"])
        mock_release.assert_called_once_with(
            self.local, 99, current_session_id=unittest.mock.ANY, force=True
        )

    @patch("sys.stdout", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.claim_issue")
    def test_cli_claim_acquire_success(self, mock_claim, mock_stdout):
        from solomon_harness.cli import main
        mock_claim.return_value = True

        main(harness_dir=self.local, argv=["claim", "acquire", "99"])
        mock_claim.assert_called_once()
        self.assertIn("Claimed issue #99", mock_stdout.getvalue())

    @patch("sys.stderr", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.get_claim_ref")
    @patch("solomon_harness.claim.claim_issue")
    def test_cli_claim_acquire_refused_names_holder_and_exits_1(
        self, mock_claim, mock_get_ref, mock_stderr
    ):
        from solomon_harness.cli import main
        mock_claim.return_value = False
        mock_get_ref.return_value = (
            "sha1",
            {
                "session_id": "other-session",
                "acquired_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )

        with self.assertRaises(SystemExit) as ctx:
            main(harness_dir=self.local, argv=["claim", "acquire", "99"])
        self.assertEqual(ctx.exception.code, 1)
        err = mock_stderr.getvalue()
        self.assertIn("other-session", err)
        self.assertIn("age:", err)

    @patch("sys.stderr", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.get_claim_ref", return_value=None)
    @patch("solomon_harness.claim.claim_issue", return_value=False)
    def test_cli_claim_acquire_proceeds_when_no_claims_remote(
        self, mock_claim, mock_get_ref, mock_stderr
    ):
        # Interactive and headless must share the no-op-environment semantics:
        # a refusal with NO ref present means no reachable claims remote, and
        # the session proceeds without a claim (exit 0) instead of being
        # permanently blocked where headless would run.
        from solomon_harness.cli import main
        main(harness_dir=self.local, argv=["claim", "acquire", "99"])
        self.assertIn("proceeding without one", mock_stderr.getvalue())

    @patch("sys.stdout", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.get_claim_ref", return_value=("sha1", None))
    def test_cli_claim_status_reports_malformed_ref(self, mock_get_ref, mock_stdout):
        # A poisoned ref must not read as "unclaimed" to an operator.
        from solomon_harness.cli import main
        main(harness_dir=self.local, argv=["claim", "status", "99"])
        out = mock_stdout.getvalue()
        self.assertIn("MALFORMED", out)
        self.assertIn("--force", out)


class TestMalformedClaimRefRecovery(unittest.TestCase):
    """A poisoned refs/claims/issue-N blob must be recoverable, not a
    permanent, silently-lying denial of service (review finding 215-m1,
    reproduced live against a bare origin)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin = os.path.join(self.tmp, "origin.git")
        self.local = os.path.join(self.tmp, "local")
        _git(None, "init", "--bare", "-q", self.origin)
        _git(None, "clone", "-q", self.origin, self.local)
        _git(self.local, "config", "user.email", "t@example.com")
        _git(self.local, "config", "user.name", "Test")
        with open(os.path.join(self.local, "README.md"), "w") as f:
            f.write("test")
        _git(self.local, "add", "README.md")
        _git(self.local, "commit", "-q", "-m", "initial commit")
        _git(self.local, "push", "-q", "origin", "HEAD:refs/heads/main")
        for target, kwargs in (
            ("solomon_harness.claim.has_active_pr_or_review", {"return_value": False}),
            ("solomon_harness.github._gh", {"return_value": {"ok": True, "stdout": ""}}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _push_garbage_claim(self, issue: int) -> None:
        tree_sha = _git(self.local, "write-tree").stdout.strip()
        commit_sha = _git(
            self.local, "commit-tree", "-m", "not json at all, garbage claim blob", tree_sha
        ).stdout.strip()
        _git(self.local, "push", "-q", "origin", f"{commit_sha}:refs/claims/issue-{issue}")

    def _ref_on_origin(self, issue: int) -> bool:
        res = _git(self.local, "ls-remote", "origin", f"refs/claims/issue-{issue}")
        return f"refs/claims/issue-{issue}" in (res.stdout or "")

    def test_get_claim_ref_distinguishes_malformed_from_absent(self):
        self.assertIsNone(claim.get_claim_ref(self.local, 777))
        self._push_garbage_claim(777)
        ref_info = claim.get_claim_ref(self.local, 777)
        self.assertIsNotNone(ref_info)
        sha, claim_dict = ref_info
        self.assertTrue(sha)
        self.assertIsNone(claim_dict)

    def test_malformed_ref_is_reclaimable(self):
        self._push_garbage_claim(777)
        self.assertTrue(claim.claim_issue(self.local, 777, current_session_id="sess-b"))
        c = claim.get_claim(self.local, 777)
        self.assertIsNotNone(c)
        self.assertEqual(c["session_id"], "sess-b")

    def test_release_actually_deletes_a_malformed_ref(self):
        # The false-recovery regression: release must delete the poisoned ref,
        # not report success while it survives on origin.
        self._push_garbage_claim(777)
        self.assertTrue(claim.release_claim(self.local, 777, current_session_id="sess-b"))
        self.assertFalse(self._ref_on_origin(777))


class TestReleaseFailClosed(unittest.TestCase):
    """release_claim must guard the same PR/review invariant claim_issue's
    reclaim path guards (review finding 215-m2): fail closed on liveness
    uncertainty, refuse a foreign ACTIVE claim without --force."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin = os.path.join(self.tmp, "origin.git")
        self.local = os.path.join(self.tmp, "local")
        _git(None, "init", "--bare", "-q", self.origin)
        _git(None, "clone", "-q", self.origin, self.local)
        _git(self.local, "config", "user.email", "t@example.com")
        _git(self.local, "config", "user.name", "Test")
        with open(os.path.join(self.local, "README.md"), "w") as f:
            f.write("test")
        _git(self.local, "add", "README.md")
        _git(self.local, "commit", "-q", "-m", "initial commit")
        _git(self.local, "push", "-q", "origin", "HEAD:refs/heads/main")
        gh_patcher = patch(
            "solomon_harness.github._gh", return_value={"ok": True, "stdout": ""}
        )
        gh_patcher.start()
        self.addCleanup(gh_patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _ref_on_origin(self, issue: int) -> bool:
        res = _git(self.local, "ls-remote", "origin", f"refs/claims/issue-{issue}")
        return f"refs/claims/issue-{issue}" in (res.stdout or "")

    def test_release_refuses_foreign_active_claim_without_force(self):
        self.assertTrue(claim.claim_issue(self.local, 88, current_session_id="sess-a"))
        with patch("solomon_harness.claim._pr_liveness", return_value=(False, False)):
            self.assertFalse(claim.release_claim(self.local, 88, current_session_id="sess-b"))
        self.assertTrue(self._ref_on_origin(88))

    def test_release_fails_closed_when_liveness_uncertain(self):
        # Even a TTL-stale foreign claim must not be releasable while its
        # PR/review protection cannot be confirmed.
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        stale = {"session_id": "sess-a", "acquired_at": past, "heartbeat_at": past}
        tree_sha = _git(self.local, "write-tree").stdout.strip()
        commit_sha = _git(self.local, "commit-tree", "-m", json.dumps(stale), tree_sha).stdout.strip()
        _git(self.local, "push", "-q", "origin", f"{commit_sha}:refs/claims/issue-88")

        with patch("solomon_harness.claim._pr_liveness", return_value=(False, True)):
            self.assertFalse(claim.release_claim(self.local, 88, current_session_id="sess-b"))
        self.assertTrue(self._ref_on_origin(88))

    def test_force_release_clears_foreign_active_claim(self):
        self.assertTrue(claim.claim_issue(self.local, 88, current_session_id="sess-a"))
        self.assertTrue(
            claim.release_claim(self.local, 88, current_session_id="sess-b", force=True)
        )
        self.assertFalse(self._ref_on_origin(88))


class TestPrLivenessBoardPaths(unittest.TestCase):
    """The confirmed-protected and degrade paths of _pr_liveness (review
    finding 215-b4: these lines had zero coverage), plus the shared board
    fetch that removes the per-issue N+1 (215-m6)."""

    def test_confirmed_protected_when_board_card_in_code_review(self):
        board = [{"content": {"number": 99}, "status": "Code Review"}]
        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": True, "data": {"state": "OPEN"}},
        ):
            protected, uncertain = claim._pr_liveness("/tmp", 99, board_items=board)
        self.assertTrue(protected)
        self.assertFalse(uncertain)

    def test_uncertain_when_board_fetch_fails(self):
        with (
            patch(
                "solomon_harness.github._gh",
                return_value={"ok": True, "data": {"state": "OPEN"}},
            ),
            patch("solomon_harness.claim.fetch_board_items", return_value=None),
        ):
            protected, uncertain = claim._pr_liveness("/tmp", 99)
        self.assertFalse(protected)
        self.assertTrue(uncertain)

    def test_fetch_board_items_degrades_to_none_on_exception(self):
        with patch("solomon_harness.github.repo_owner", side_effect=RuntimeError("boom")):
            self.assertIsNone(claim.fetch_board_items("/tmp"))

    def test_protected_claim_blocks_reclaim(self):
        # A TTL-stale claim whose board card sits in Code Review must not be
        # reclaimable: the protected path, end to end through claim_issue.
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        stale = {"session_id": "sess-a", "acquired_at": past, "heartbeat_at": past}
        with (
            patch("solomon_harness.claim.get_claim_ref", return_value=("sha1", stale)),
            patch("solomon_harness.claim._pr_liveness", return_value=(True, False)),
        ):
            self.assertFalse(claim.claim_issue("/tmp", 99, current_session_id="sess-b"))

    def test_filter_unclaimed_keeps_stale_and_own_claims(self):
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        stale_foreign = {"session_id": "sess-a", "acquired_at": past, "heartbeat_at": past}
        fresh = datetime.datetime.now(datetime.timezone.utc).isoformat()
        own = {"session_id": "me", "acquired_at": fresh, "heartbeat_at": fresh}
        with (
            patch(
                "solomon_harness.claim.fetch_all_claims",
                return_value={5: stale_foreign, 6: own},
            ),
            patch("solomon_harness.claim.fetch_board_items", return_value=[]),
        ):
            result = claim.filter_unclaimed("/tmp", [5, 6, 7], current_session_id="me")
        self.assertEqual(result, [5, 6, 7])

    def test_filter_unclaimed_fetches_the_board_once_for_many_claims(self):
        fresh = datetime.datetime.now(datetime.timezone.utc).isoformat()
        claims = {
            n: {"session_id": f"sess-{n}", "acquired_at": fresh, "heartbeat_at": fresh}
            for n in (1, 2, 3)
        }
        with (
            patch("solomon_harness.claim.fetch_all_claims", return_value=claims),
            patch(
                "solomon_harness.claim.fetch_board_items", return_value=[]
            ) as mock_board,
        ):
            claim.filter_unclaimed("/tmp", [1, 2, 3], current_session_id="me")
        mock_board.assert_called_once()

    def test_filter_unclaimed_caches_a_failed_board_fetch_too(self):
        # A failed board fetch returns None -- which is also _pr_liveness's
        # "fetch here" sentinel. The failure must be cached like a success,
        # or the N+1 comes back exactly when gh is failing.
        fresh = datetime.datetime.now(datetime.timezone.utc).isoformat()
        claims = {
            n: {"session_id": f"sess-{n}", "acquired_at": fresh, "heartbeat_at": fresh}
            for n in (1, 2, 3)
        }
        with (
            patch("solomon_harness.claim.fetch_all_claims", return_value=claims),
            patch(
                "solomon_harness.claim.fetch_board_items", return_value=None
            ) as mock_board,
            patch("solomon_harness.claim._pr_liveness") as mock_liveness,
        ):
            claim.filter_unclaimed("/tmp", [1, 2, 3], current_session_id="me")
        mock_board.assert_called_once()
        mock_liveness.assert_not_called()


class TestRunStageClaimLifecycle(unittest.TestCase):
    """run_stage's heartbeat-loss abort and failed-run claim release (review
    findings 215-b3 residue and the loop_engineer majors)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.local = os.path.join(self.tmp, "local")
        os.makedirs(self.local)
        _git(None, "init", "-q", self.local)
        read_patcher = patch(
            "solomon_harness.workflows._read_command_file",
            return_value="---\nallowed-tools: Bash\n---\nbody",
        )
        read_patcher.start()
        self.addCleanup(read_patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @patch("solomon_harness.claim.release_claim")
    @patch("solomon_harness.claim.refresh_claim", return_value=False)
    @patch("solomon_harness.claim.claim_issue", return_value=True)
    @patch("solomon_harness.claim.has_active_pr_or_review", return_value=False)
    @patch("solomon_harness.claim.get_claim", return_value=None)
    def test_confirmed_heartbeat_loss_fails_the_stage(
        self, mock_get, mock_pr, mock_claim, mock_refresh, mock_release
    ):
        # The engine exits 0, but the claim was confirmed taken over mid-run:
        # the stage must be marked failed, and the (no longer ours) claim must
        # NOT be released by the finally.
        import time
        from solomon_harness import workflows

        class _Proc:
            returncode = 0

        def _slow_engine(*args, **kwargs):
            time.sleep(0.4)
            return _Proc()

        with (
            patch.object(claim, "CLAIM_HEARTBEAT_INTERVAL_SECONDS", 0.05),
            patch("subprocess.run", side_effect=_slow_engine),
        ):
            rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")

        self.assertEqual(rc, 1)
        mock_refresh.assert_called()
        mock_release.assert_not_called()

    @patch("solomon_harness.claim.release_claim")
    @patch("solomon_harness.claim.claim_issue", return_value=True)
    @patch("solomon_harness.claim.has_active_pr_or_review", return_value=False)
    @patch("solomon_harness.claim.get_claim", return_value=None)
    def test_failed_run_releases_its_own_claim(
        self, mock_get, mock_pr, mock_claim, mock_release
    ):
        from solomon_harness import workflows

        class _Proc:
            returncode = 2

        with patch("subprocess.run", return_value=_Proc()):
            rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")

        self.assertEqual(rc, 2)
        mock_release.assert_called_once()
        _, kwargs = mock_release.call_args
        self.assertNotIn("force", kwargs)

    @patch("solomon_harness.claim.release_claim")
    @patch("solomon_harness.claim.claim_issue", return_value=True)
    @patch("solomon_harness.claim.has_active_pr_or_review", return_value=False)
    @patch("solomon_harness.claim.get_claim", return_value=None)
    def test_successful_run_keeps_its_claim(
        self, mock_get, mock_pr, mock_claim, mock_release
    ):
        from solomon_harness import workflows

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()):
            rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")

        self.assertEqual(rc, 0)
        mock_release.assert_not_called()

    @patch("solomon_harness.claim.release_claim")
    @patch("solomon_harness.claim.claim_issue", return_value=True)
    @patch("solomon_harness.claim.has_active_pr_or_review", return_value=False)
    @patch("solomon_harness.claim.get_claim", return_value=None)
    def test_missing_engine_still_releases_the_claim(
        self, mock_get, mock_pr, mock_claim, mock_release
    ):
        # Verifier regression (round 3): a FileNotFoundError from the engine
        # spawn returned 1 while the local rc still read 0, so the finally
        # skipped the release and the claim survived for the whole TTL.
        from solomon_harness import workflows

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")

        self.assertEqual(rc, 1)
        mock_release.assert_called_once()

    @patch("sys.stderr", new_callable=lambda: StringIO())
    @patch("solomon_harness.claim.is_claim_active", return_value=True)
    @patch("solomon_harness.claim.has_active_pr_or_review", return_value=False)
    @patch("solomon_harness.claim.get_claim")
    def test_blocked_start_names_holder_and_age(
        self, mock_get, mock_pr, mock_active, mock_stderr
    ):
        # Acceptance criterion #2 of issue #51: the refusal names the holder
        # and the claim age, so the second session knows who and how long.
        from solomon_harness import workflows

        mock_get.return_value = {
            "session_id": "other-session",
            "acquired_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        rc = workflows.run_stage(self.local, "start", ["99"], engine="claude")
        self.assertEqual(rc, 1)
        err = mock_stderr.getvalue()
        self.assertIn("other-session", err)
        self.assertIn("claim age", err)


class TestClaimConcurrency(unittest.TestCase):
    """review-215-b5d: N sessions race one issue against one origin -> exactly one wins.

    The mutual-exclusion guarantee rests on git ``push --force-with-lease``
    atomicity -- git's own, verified empirically during the #215 review. The
    sequential tests never exercise a real race, so this locks the guarantee in
    against a future refactor of ``claim_issue``'s internal ordering. Each
    session uses its OWN clone of a shared bare origin: the real production
    shape (independent worktrees/sessions pushing to one GitHub origin).
    """

    N = 5

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin = os.path.join(self.tmp, "origin.git")
        _git(None, "init", "--bare", "-q", self.origin)

        seed = os.path.join(self.tmp, "seed")
        _git(None, "clone", "-q", self.origin, seed)
        _git(seed, "config", "user.email", "t@example.com")
        _git(seed, "config", "user.name", "Test")
        with open(os.path.join(seed, "README.md"), "w") as f:
            f.write("seed")
        _git(seed, "add", "README.md")
        _git(seed, "commit", "-q", "-m", "seed")
        _git(seed, "push", "-q", "origin", "HEAD:refs/heads/main")

        self.clones = []
        for i in range(self.N):
            path = os.path.join(self.tmp, f"clone-{i}")
            _git(None, "clone", "-q", self.origin, path)
            _git(path, "config", "user.email", "t@example.com")
            _git(path, "config", "user.name", "Test")
            self.clones.append(path)

        # Isolate every thread from GitHub (mirrors TestClaimGitOperations):
        # claim_issue consults _pr_liveness and edits the assignee via _gh.
        for target, kwargs in (
            ("solomon_harness.claim.has_active_pr_or_review", {"return_value": False}),
            ("solomon_harness.claim._pr_liveness", {"return_value": (False, False)}),
            ("solomon_harness.github._gh", {"return_value": {"ok": True, "stdout": ""}}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_exactly_one_session_wins_a_concurrent_race(self):
        import threading

        results = {}
        errors = {}
        start = threading.Barrier(self.N)

        def _attempt(i):
            try:
                start.wait(timeout=10)  # release all threads at once -> real contention
                results[i] = claim.claim_issue(
                    self.clones[i], 99, current_session_id=f"sess-{i}"
                )
            except Exception as exc:  # noqa: BLE001 - a racing thread must never crash the test
                errors[i] = repr(exc)

        threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(self.N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, {}, f"no racing thread should raise: {errors}")
        self.assertEqual(len(results), self.N, "every thread recorded a result")
        winners = [i for i, ok in results.items() if ok]
        self.assertEqual(
            len(winners), 1, f"exactly one winner expected, got {winners} (results={results})"
        )
        # The origin records exactly the winner's session id, not a loser's.
        recorded = claim.get_claim(self.clones[winners[0]], 99)
        self.assertIsNotNone(recorded)
        self.assertEqual(recorded.get("session_id"), f"sess-{winners[0]}")

    def _seed_stale_claim(self, issue_number, owner):
        """Push a past-TTL claim commit onto the origin's claim ref."""
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
        ).isoformat()
        claim_data = {"session_id": owner, "acquired_at": past, "heartbeat_at": past}
        seed = os.path.join(self.tmp, "stale-seed")
        _git(None, "clone", "-q", self.origin, seed)
        _git(seed, "config", "user.email", "t@example.com")
        _git(seed, "config", "user.name", "Test")
        tree = _git(seed, "write-tree").stdout.strip()
        commit = _git(seed, "commit-tree", "-m", json.dumps(claim_data), tree).stdout.strip()
        _git(seed, "push", "-q", "origin", f"{commit}:refs/claims/issue-{issue_number}")

    def test_exactly_one_session_wins_a_stale_reclaim_race(self):
        # Seed a past-TTL claim so every racer exercises the RECLAIM branch
        # (claim_issue's `existing_sha` push with --force-with-lease={ref}:{sha}),
        # which the fresh-claim race never touches. This asserts the observable
        # end-to-end guarantee: exactly one of N distinct sessions reclaims a
        # stale claim, and the stale owner is replaced.
        #
        # Note on what actually enforces this: under a real race the primary
        # guard is claim_issue's is_claim_active recheck (a racer whose fetch
        # lands after the winner's reclaim sees a fresh, active claim and bails
        # before pushing). The git CAS lease is defense-in-depth for the
        # narrower window where two sessions fetch the SAME stale sha at the same
        # instant and both reach the push -- a window this test cannot force
        # deterministically (the fetch happens inside claim_issue, after the
        # Barrier), so this test does not, on its own, isolate the lease. The
        # fresh-claim race above is the one that catches a broken push signal.
        import threading

        self._seed_stale_claim(99, "sess-old")
        results = {}
        errors = {}
        start = threading.Barrier(self.N)

        def _attempt(i):
            try:
                start.wait(timeout=10)
                results[i] = claim.claim_issue(
                    self.clones[i], 99, current_session_id=f"sess-{i}"
                )
            except Exception as exc:  # noqa: BLE001 - a racing thread must never crash the test
                errors[i] = repr(exc)

        threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(self.N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, {}, f"no racing thread should raise: {errors}")
        self.assertEqual(len(results), self.N, "every thread recorded a result")
        winners = [i for i, ok in results.items() if ok]
        self.assertEqual(
            len(winners), 1, f"exactly one reclaimer expected, got {winners} (results={results})"
        )
        recorded = claim.get_claim(self.clones[winners[0]], 99)
        self.assertIsNotNone(recorded)
        self.assertEqual(recorded.get("session_id"), f"sess-{winners[0]}")
        self.assertNotEqual(
            recorded.get("session_id"), "sess-old", "the stale owner must have been replaced"
        )


if __name__ == '__main__':
    from io import StringIO
    unittest.main()
