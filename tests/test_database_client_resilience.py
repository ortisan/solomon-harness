"""Connection-resilience tests for DatabaseClient (issue #37).

These exercise the SurrealDB path hermetically: a client is built SQLite-isolated
(db_path on a temp file) and then switched to the SurrealDB branch by setting
``client.backend = "surrealdb"`` and ``client.db = FakeSurreal(...)``. The fake's
``query`` is programmed to raise a transport fault once, always, or to raise a
genuine query/data error, so the reconnect/fallback policy is verified without a
live backend or Docker (coordinating with the hermeticity guard from #36).
"""

import os
import sys
import tempfile
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402


# The exact transport symptom observed in the v0.3.0 incident.
TRANSPORT_ERROR = "no close frame received or sent"


class FakeSurreal:
    """A programmable stand-in for a SurrealDB connection handle.

    Modes (checked in order on every ``query`` call):
    - ``query_error``: raise a genuine query/data error (no connection markers).
    - ``always_fail``: raise the transport error on every call (unreachable).
    - ``fail_remaining``: raise the transport error this many times, then succeed.
    Otherwise return ``result`` (a value, or a callable ``(query, params) -> value``).
    """

    def __init__(self, result=None):
        self.fail_remaining = 0
        self.always_fail = False
        self.query_error = False
        self.result = [] if result is None else result
        self.calls = []
        self.closed = False

    def query(self, query, params=None):
        self.calls.append((query, params))
        if self.query_error:
            raise Exception("Parse error: unexpected token near 'SELEC'")
        if self.always_fail:
            raise Exception(TRANSPORT_ERROR)
        if self.fail_remaining > 0:
            self.fail_remaining -= 1
            raise Exception(TRANSPORT_ERROR)
        if callable(self.result):
            return self.result(query, params)
        return self.result

    def close(self):
        self.closed = True


class ResilienceTestBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _surreal_client(self, fake):
        """Build a SQLite-isolated client, then switch it to the SurrealDB branch
        backed by ``fake`` so the resilience path can be driven deterministically."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.backend = "surrealdb"
        client.db = fake
        return client


class TestReconnectOnce(ResilienceTestBase):
    def test_write_after_drop_reconnects_once_and_returns_id(self):
        # The live connection drops: the next query raises the transport error.
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._surreal_client(broken)

        reconnect_calls = []

        def fake_reconnect():
            # A successful reconnect rebuilds the handle against a reachable server.
            reconnect_calls.append(1)
            client.db = FakeSurreal(result=[[{"id": "decisions:1"}]])
            return True

        client._connect_surreal = fake_reconnect

        decision_id = client.log_decision(
            title="t",
            rationale="r",
            outcome="o",
            author="po",
            branch="b",
            commit_sha="sha",
        )

        self.assertEqual(decision_id, "decisions:1")
        self.assertEqual(len(reconnect_calls), 1, "must reconnect exactly once")
        self.assertEqual(client.backend, "surrealdb", "a reachable server must not fall back")


if __name__ == "__main__":
    unittest.main()
