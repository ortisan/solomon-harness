import unittest
from unittest.mock import patch, MagicMock
import datetime
import os
import shutil
import tempfile
import subprocess
import json

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

if __name__ == '__main__':
    unittest.main()
