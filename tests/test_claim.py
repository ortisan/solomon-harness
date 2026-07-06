import unittest
from unittest.mock import patch, MagicMock
import datetime

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
        # Current time 1000.0, heartbeat at 900.0 (100s ago)
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        # mock current time: 2026-07-06T00:20:00Z (10 minutes after heartbeat, within 30-min TTL)
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        self.assertTrue(claim.is_claim_active(claim_data, current_session_id="session-456", now=now))

    def test_is_claim_inactive_past_ttl_without_pr(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        # mock current time: 2026-07-06T00:50:00Z (40 minutes after heartbeat, past 30-min TTL)
        now = datetime.datetime.fromisoformat("2026-07-06T00:50:00Z")
        # No active PR or special status
        self.assertFalse(claim.is_claim_active(claim_data, current_session_id="session-456", now=now, has_open_pr=False))

    def test_is_claim_active_past_ttl_with_active_pr(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:50:00Z")
        # Has active PR, so liveness is tied to the PR state, blocking reclaim!
        self.assertTrue(claim.is_claim_active(claim_data, current_session_id="session-456", now=now, has_open_pr=True))

    def test_same_session_is_not_active_blocking(self):
        claim_data = {
            "session_id": "session-123",
            "acquired_at": "2026-07-06T00:00:00Z",
            "heartbeat_at": "2026-07-06T00:10:00Z",
        }
        now = datetime.datetime.fromisoformat("2026-07-06T00:20:00Z")
        # Same session re-entry is always allowed/not blocked
        self.assertFalse(claim.is_claim_active(claim_data, current_session_id="session-123", now=now))

if __name__ == '__main__':
    unittest.main()
