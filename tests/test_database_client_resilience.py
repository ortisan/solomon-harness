"""Connection-resilience tests for DatabaseClient (issue #37).

These exercise the SurrealDB path hermetically: a client is built SQLite-isolated
(db_path on a temp file) and then switched to the SurrealDB branch by setting
``client.backend = "surrealdb"`` and ``client.db = FakeSurreal(...)``. The fake's
``query`` is programmed to raise a transport fault once, always, or to raise a
genuine query/data error, so the reconnect/fallback policy is verified without a
live backend or Docker (coordinating with the hermeticity guard from #36).
"""

import glob
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    DatabaseClient,
    _ConnectionLost,
)


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


class TestUnreachableFallsBackToSqlite(ResilienceTestBase):
    def test_write_unreachable_falls_back_to_sqlite_bounded(self):
        # The connection is dropped and the server stays unreachable.
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._surreal_client(broken)

        reconnect_calls = []

        def fake_reconnect():
            reconnect_calls.append(1)
            return False  # the single reconnect attempt fails

        client._connect_surreal = fake_reconnect

        stderr = io.StringIO()
        start = time.monotonic()
        with redirect_stderr(stderr):
            decision_id = client.log_decision(
                title="t",
                rationale="r",
                outcome="o",
                author="po",
                branch="b",
                commit_sha="sha",
            )
        elapsed = time.monotonic() - start

        self.assertIsNotNone(decision_id, "the fallback write must persist and return an id")
        self.assertEqual(client.backend, "sqlite", "a failed reconnect must fall back to SQLite")
        self.assertEqual(len(reconnect_calls), 1, "exactly one reconnect attempt before fallback")
        self.assertLess(elapsed, 5.0, "the dropped+unreachable path must be bounded, never hang")
        # The SurrealDB/SQLite divergence must be announced loudly, not silently.
        self.assertIn("sqlite", stderr.getvalue().lower())
        # The write is durable: it is readable back from the SQLite fallback.
        persisted = client.get_decision(decision_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["title"], "t")


class TestGetLatestActivityNeverSilentNull(ResilienceTestBase):
    def test_reconnects_and_returns_real_activity(self):
        # The read fires on a dropped connection; the reconnect succeeds and the
        # real recorded activity is returned -- never a masked None (the dangerous
        # fault that drove /solomon-workflow to the wrong resume point).
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._surreal_client(broken)

        def healthy_query(query, params=None):
            if "sessions" in query:
                return [
                    [
                        {
                            "session_id": "s1",
                            "agent_name": "agent_x",
                            "task": "task_x",
                            "timestamp": "2026-06-28T22:00:00",
                        }
                    ]
                ]
            return []  # no handoffs

        reconnect_calls = []

        def fake_reconnect():
            reconnect_calls.append(1)
            client.db = FakeSurreal(result=healthy_query)
            return True

        client._connect_surreal = fake_reconnect

        activity = client.get_latest_activity()

        self.assertIsNotNone(activity, "a broken connection must not mask as None")
        self.assertEqual(activity["type"], "session")
        self.assertEqual(activity["agent"], "agent_x")
        self.assertEqual(len(reconnect_calls), 1)
        self.assertEqual(client.backend, "surrealdb")

    def test_falls_back_and_returns_real_activity(self):
        # Activity recorded before the drop is still served via the SQLite fallback
        # when the reconnect fails -- still a non-null result, not a masked None.
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.save_session("s1", "agent_x", "task_x", [])

        client.backend = "surrealdb"
        broken = FakeSurreal()
        broken.always_fail = True
        client.db = broken
        client._connect_surreal = lambda: False

        with redirect_stderr(io.StringIO()):
            activity = client.get_latest_activity()

        self.assertIsNotNone(activity, "a broken connection must not mask as None")
        self.assertEqual(activity["agent"], "agent_x")
        self.assertEqual(client.backend, "sqlite")

    def test_true_empty_store_still_returns_none(self):
        # A healthy but genuinely empty store returns None and must not be confused
        # for a broken connection: no reconnect, no fallback.
        healthy = FakeSurreal(result=[])
        client = self._surreal_client(healthy)

        reconnect_calls = []

        def fake_reconnect():
            reconnect_calls.append(1)
            return True

        client._connect_surreal = fake_reconnect

        activity = client.get_latest_activity()

        self.assertIsNone(activity, "a genuinely empty store still returns None")
        self.assertEqual(len(reconnect_calls), 0, "a true empty must not reconnect")
        self.assertEqual(client.backend, "surrealdb", "a true empty must not fall back")


class TestGetLatestActivityPreservesContractPath(ResilienceTestBase):
    def test_handoff_then_session_still_surfaces_contract_path(self):
        # Every /solomon-* command logs a handoff immediately followed by a
        # session save (see .claude/commands/solomon-start.md and friends), so
        # in the ordinary case the session row's timestamp is equal to or later
        # than the handoff row's. get_latest_activity must not let the
        # session-shaped result silently drop the handoff's contract_path --
        # doing so defeats the bounded-context handoff mechanism documented in
        # docs/solomon-workflow.md ("Handoff contracts").
        client = DatabaseClient(db_path=self.sqlite_db_path)

        client.log_handoff(
            sender="product_owner",
            recipient="scrum_master",
            contract_type="plan",
            contract_path="/some/path/plan.md",
            status="pending",
        )
        client.save_session(
            session_id="sess-1",
            agent_name="scrum_master",
            task="Refine backlog",
            messages=[],
        )

        activity = client.get_latest_activity()

        self.assertIsNotNone(activity)
        self.assertIsNotNone(
            activity.get("contract_path"),
            "the latest handoff's contract_path must survive even when the "
            "session row wins the timestamp comparison",
        )
        self.assertEqual(activity["contract_path"], "/some/path/plan.md")

    def test_handoff_summary_survives_contract_file_deletion(self):
        # Issue #295: summary is the documented fallback for when contract_path
        # no longer resolves (its worktree torn down after merge). A resume via
        # get_latest_activity must still surface the non-empty summary, and
        # must not raise just because the file the path points to is gone.
        client = DatabaseClient(db_path=self.sqlite_db_path)
        contract_path = os.path.join(
            self.temp_dir.name, "issue-214-start-to-review.md"
        )
        with open(contract_path, "w", encoding="utf-8") as f:
            f.write("# Handoff: start -> review - issue #214\n")

        client.log_handoff(
            sender="software_engineer",
            recipient="qa",
            contract_type="pull_request",
            contract_path=contract_path,
            status="open",
            summary="qa approved PR #214, merged to main",
        )

        os.remove(contract_path)
        self.assertFalse(os.path.exists(contract_path))

        activity = client.get_latest_activity()

        self.assertIsNotNone(activity)
        self.assertEqual(
            activity.get("summary"), "qa approved PR #214, merged to main"
        )
        self.assertEqual(activity.get("contract_path"), contract_path)

    def test_session_wins_still_surfaces_handoff_summary(self):
        # Issue #305: the session-wins branch (the routine case, since every
        # /solomon-* command logs a handoff immediately followed by a session
        # save) already surfaces the latest handoff's contract_path, but was
        # silently dropping its summary. That nullifies #295's guarantee on
        # the path that fires most of the time. Both fields must survive
        # together when the session row wins the timestamp comparison.
        client = DatabaseClient(db_path=self.sqlite_db_path)

        client.log_handoff(
            sender="software_engineer",
            recipient="qa",
            contract_type="pull_request",
            contract_path="/some/path/plan.md",
            status="open",
            summary="qa approved PR #214",
        )
        client.save_session(
            session_id="sess-305",
            agent_name="qa",
            task="Review PR #214",
            messages=[],
        )

        activity = client.get_latest_activity()

        self.assertIsNotNone(activity)
        self.assertEqual(activity["type"], "session")
        self.assertEqual(activity.get("summary"), "qa approved PR #214")
        self.assertEqual(activity.get("contract_path"), "/some/path/plan.md")


class TestQueryErrorIsNotConnectionLoss(ResilienceTestBase):
    def test_run_surreal_classifies_transport_versus_query_error(self):
        # _run_surreal converts only a transport fault into _ConnectionLost; a
        # genuine query/data error is re-raised unchanged so it cannot trigger a
        # reconnect or a fallback that would mask a real bug.
        transport = FakeSurreal()
        transport.always_fail = True
        client = self._surreal_client(transport)
        with self.assertRaises(_ConnectionLost):
            client._run_surreal("SELECT * FROM decisions")

        data_error = FakeSurreal()
        data_error.query_error = True
        client.db = data_error
        with self.assertRaises(Exception) as ctx:
            client._run_surreal("SELECT * FROM decisions")
        self.assertNotIsInstance(ctx.exception, _ConnectionLost)

    def test_query_error_does_not_reconnect_or_fall_back(self):
        fake = FakeSurreal()
        fake.query_error = True  # not a transport fault
        client = self._surreal_client(fake)

        reconnect_calls = []

        def fake_reconnect():
            reconnect_calls.append(1)
            return True

        client._connect_surreal = fake_reconnect

        # The query error must surface as before (the SurrealDB branch wraps it),
        # not be swallowed by a reconnect or a fallback.
        with self.assertRaises(RuntimeError):
            client.log_decision(
                title="t",
                rationale="r",
                outcome="o",
                author="po",
                branch="b",
                commit_sha="sha",
            )

        self.assertEqual(len(reconnect_calls), 0, "a query/data error must not reconnect")
        self.assertEqual(client.backend, "surrealdb", "a query/data error must not fall back")


class TestConnectionErrorClassification(ResilienceTestBase):
    """``_is_connection_error`` must key off exception TYPE first and fall back to
    only narrow, anchored transport phrases. A query/data error that merely
    contains the words "connection" or "closed" must not be read as a drop, or it
    would silently reconnect/fall back and mask a real bug (#37)."""

    # A genuine data error that happens to mention the loaded words in passing.
    DATA_ERROR_WITH_CONN_WORDS = (
        "data error: the connection pool field is now closed for new rows"
    )

    def test_data_error_mentioning_connection_words_is_not_a_drop(self):
        exc = Exception(self.DATA_ERROR_WITH_CONN_WORDS)
        self.assertFalse(DatabaseClient._is_connection_error(exc))

    def test_incident_no_close_frame_is_still_a_drop(self):
        # The exact v0.3.0 symptom must keep classifying as a transport fault.
        self.assertTrue(DatabaseClient._is_connection_error(Exception(TRANSPORT_ERROR)))

    def test_oserror_is_a_drop_by_type(self):
        self.assertTrue(DatabaseClient._is_connection_error(ConnectionResetError("reset")))

    def test_surreal_connection_exception_is_a_drop_by_type(self):
        try:
            from surrealdb.errors import ConnectionUnavailableError
        except Exception:  # pragma: no cover - SDK without the class
            self.skipTest("surrealdb ConnectionUnavailableError not importable")
        # Even with a benign message, the connection TYPE marks it a drop.
        self.assertTrue(
            DatabaseClient._is_connection_error(ConnectionUnavailableError("oops"))
        )

    def test_data_error_with_conn_words_does_not_reconnect_or_fall_back(self):
        def raise_data_error(query, params=None):
            raise Exception(self.DATA_ERROR_WITH_CONN_WORDS)

        client = self._surreal_client(FakeSurreal(result=raise_data_error))

        reconnect_calls = []

        def fake_reconnect():
            reconnect_calls.append(1)
            return True

        client._connect_surreal = fake_reconnect

        with self.assertRaises(RuntimeError):
            client.log_decision(
                title="t",
                rationale="r",
                outcome="o",
                author="po",
                branch="b",
                commit_sha="sha",
            )

        self.assertEqual(len(reconnect_calls), 0, "a data error must not reconnect")
        self.assertEqual(client.backend, "surrealdb", "a data error must not fall back")


class TestConnectIsBoundedAndCannotHang(ResilienceTestBase):
    """The anti-hang core of #37: a wedged handshake must not block past the
    deadline. Every other resilience test stubs ``_connect_surreal`` out, so this
    drives the real method against a Surreal factory whose connect/signin block on
    an Event that is never set -- the exact "no close frame" half-open socket that
    motivated the bounded worker-thread + join(deadline). Removing the deadline (or
    the worker thread) would hang here forever, failing the < 2s bound."""

    def test_connect_returns_false_within_deadline_when_handshake_blocks(self):
        never = threading.Event()  # deliberately never set: the handshake wedges

        class BlockingSurreal:
            def __init__(self, url):
                self.url = url

            def connect(self):
                never.wait()  # block indefinitely, like a half-open socket

            def signin(self, creds):
                never.wait()

            def use(self, namespace, database):
                pass

        client = DatabaseClient(db_path=self.sqlite_db_path)
        # Point the reconnect machinery at the blocking factory with a tight deadline.
        client._surreal_class = BlockingSurreal
        client._surreal_url = "ws://localhost:8000/rpc"
        client._surreal_username = "root"
        client._surreal_password = "root"
        client._surreal_namespace = "solomon"
        client._surreal_database = "test"
        client._connect_deadline = 0.2

        start = time.monotonic()
        with redirect_stderr(io.StringIO()):
            result = client._connect_surreal()
        elapsed = time.monotonic() - start

        self.assertFalse(result, "a wedged handshake must not report success")
        self.assertLess(
            elapsed, 2.0, "the bounded connect must abandon the attempt, never hang"
        )
        # The handle is never adopted from a timed-out attempt.
        self.assertIsNone(client.db)


class MirroredMutationTestBase(ResilienceTestBase):
    """Base for tests that assert on the write-through mirror of a mutation.

    Same hermetic setup as the other resilience tests, plus a temp mirror root
    and a client marked as having SurrealDB configured as its primary so the
    synced/reconcile logic behaves like a real two-store client.
    """

    def setUp(self):
        super().setUp()
        self.mirror_root = os.path.join(self.temp_dir.name, "mirror")

    def _configured_client(self, fake, connect=None):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()  # mark SurrealDB as the configured primary
        client.backend = "surrealdb"
        client.db = fake
        if connect is not None:
            client._connect_surreal = connect
        return client

    def _mirror_files(self, kind):
        return sorted(glob.glob(os.path.join(self.mirror_root, kind, "*.md")))

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()


class TestSaveLoopRunResilience(MirroredMutationTestBase):
    def test_outage_falls_back_to_sqlite_and_mirrors_pending(self):
        # The connection is dropped and the server stays unreachable: the write
        # must fall back to SQLite (never raise) and leave a pending mirror entry
        # so reconcile can replay it to the primary on recovery.
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            run_id = client.save_loop_run(
                stage="dev", target="42", decision="ran dev", status="ok", session_id="s1"
            )

        self.assertIsNotNone(run_id, "the fallback write must persist and return an id")
        self.assertEqual(client.backend, "sqlite")
        rows = client.list_loop_runs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "dev")

        files = self._mirror_files("loop_run")
        self.assertEqual(len(files), 1, "an outage write must still land in the mirror")
        text = self._read(files[0])
        self.assertIn("kind: loop_run", text)
        self.assertIn("synced: false", text)
        self.assertIn('"stage": "dev"', text)

    def test_healthy_write_mirrors_synced_true_and_upserts_by_minted_id(self):
        fake = FakeSurreal(result=[[{"id": "loop_runs:1"}]])
        client = self._configured_client(fake)

        run_id = client.save_loop_run(
            stage="review", target="7", decision="ran review", status="ok", session_id="s2"
        )

        self.assertEqual(run_id, "loop_runs:1")
        files = self._mirror_files("loop_run")
        self.assertEqual(len(files), 1)
        self.assertIn("synced: true", self._read(files[0]))
        # The DB write is an UPSERT keyed by the minted id (== the mirror
        # filename) so a reconcile replay can never duplicate the record.
        minted = os.path.basename(files[0])[:-3]
        upserts = [(q, p) for q, p in fake.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        self.assertIn(minted, str(upserts[0][1]["id"]))
        self.assertTrue(str(upserts[0][1]["id"]).startswith("loop_runs:"))


class TestDeleteMemoryMirror(MirroredMutationTestBase):
    def test_delete_during_outage_tombstones_mirror_and_replay_deletes(self):
        # The resurrection scenario: a save that only reached the SQLite fallback
        # leaves a pending mirror; the delete that follows must replace it with a
        # deletion tombstone, so the recovery reconcile replays a DELETE instead
        # of UPSERTing the deleted row back into the primary.
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            client.save_memory("k1", "v1", "c")
        self.assertEqual(client.backend, "sqlite")

        client.delete_memory("k1")
        self.assertIsNone(client.get_memory("k1"))

        # The key's single mirror file is now a pending deletion tombstone; the
        # stale saved value must be gone from it.
        files = self._mirror_files("memory")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("synced: false", text)
        self.assertIn('"deleted": true', text)
        self.assertNotIn('"v1"', text)

        # On recovery the reconcile replays the deletion, never the old row.
        recovered = FakeSurreal(result=[])

        def connect():
            client.db = recovered
            return True

        client._connect_surreal = connect

        result = client.reconcile()

        self.assertEqual(result, {"synced": 1, "remaining": 0})
        upserts = [q for q, _ in recovered.calls if "UPSERT" in q]
        self.assertEqual(upserts, [], "a replayed deletion must never UPSERT the row back")
        deletes = [(q, p) for q, p in recovered.calls if "DELETE" in q]
        self.assertEqual(len(deletes), 1)
        self.assertIn("k1", str(deletes[0][1]))
        # The tombstone is re-stamped synced and stays a tombstone.
        text = self._read(files[0])
        self.assertIn("synced: true", text)
        self.assertIn('"deleted": true', text)

    def test_healthy_delete_overwrites_mirror_with_tombstone(self):
        fake = FakeSurreal(result=[])
        client = self._configured_client(fake)

        client.save_memory("k2", "v2", "c")
        client.delete_memory("k2")

        # Still exactly one mirror file for the key: the tombstone reuses the
        # key-derived filename, so no stale save survives to be replayed.
        files = self._mirror_files("memory")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("synced: true", text)
        self.assertIn('"deleted": true', text)
        self.assertNotIn('"v2"', text)
        # The live delete still hit the primary.
        self.assertTrue(any("DELETE" in q for q, _ in fake.calls))


if __name__ == "__main__":
    unittest.main()
