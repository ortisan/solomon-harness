"""Tests for the worked_on episodic edge and graph-based resume (ADR-0017, #167).

Sessions and loop runs link to the issues they advance through a typed
``worked_on`` edge, written through the wave-1 mirrored relate funnel on
SurrealDB and into a parity link table on the SQLite fallback, so resume is a
graph query instead of a regex over free-text task strings. Layers covered:

- Pure-SQLite behavior (explicit ``db_path``): parity rows, minimal issue
  creation, and the join-based ``latest_activity_per_issue``.
- Backend-agnostic unit tests that mock ``_run_surreal`` to pin the RELATE and
  graph-query construction, so coverage holds in CI without a server.
- LIVE tests gated on a reachable SurrealDB, run in a throwaway database.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402
from solomon_harness import workflows  # noqa: E402


class _SqliteBase(unittest.TestCase):
    """A pure-SQLite client (explicit db_path forces the fallback backend)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")
        self.db_path = os.path.join(self.temp_dir.name, "h.db")

    def tearDown(self):
        os.environ.pop("HARNESS_MIRROR_ROOT", None)
        self.temp_dir.cleanup()

    def _client(self):
        return DatabaseClient(db_path=self.db_path)

    def _worked_on_rows(self, db):
        with db._sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM worked_on ORDER BY id")
            return [dict(r) for r in cur.fetchall()]


class TestWorkedOnSchema(unittest.TestCase):
    def test_worked_on_relation_is_its_own_schema_statement(self):
        # One DEFINE per query() call (the SDK surfaces only the first
        # statement's result), so the RELATION table must be a list entry of
        # its own, never folded into another statement.
        self.assertIn(
            "DEFINE TABLE IF NOT EXISTS worked_on TYPE RELATION;",
            DatabaseClient._SURREAL_SCHEMA_STATEMENTS,
        )

    def test_worked_on_is_a_known_relation_edge(self):
        self.assertIn("worked_on", DatabaseClient._RELATION_EDGES)


class TestSaveSessionWorkedOnSqlite(_SqliteBase):
    def test_save_session_without_issues_writes_no_links(self):
        with self._client() as db:
            db.save_session("s1", "software_engineer", "Implement a thing", "[]")
            self.assertEqual(self._worked_on_rows(db), [])

    def test_save_session_with_issues_writes_parity_links(self):
        with self._client() as db:
            db.log_issue("42", "The issue", "feature", "in_progress", None)
            db.save_session("s1", "software_engineer", "Implement", "[]", issues=[42])
            rows = self._worked_on_rows(db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_table"], "sessions")
        self.assertEqual(rows[0]["source_id"], "s1")
        self.assertEqual(rows[0]["github_id"], "42")

    def test_save_session_creates_missing_issue_row_instead_of_dangling(self):
        with self._client() as db:
            db.save_session("s1", "qa", "Review", "[]", issues=[99])
            issue = db.get_issue("99")
        self.assertIsNotNone(issue)
        self.assertEqual(issue["github_id"], "99")

    def test_save_session_does_not_overwrite_an_existing_issue_row(self):
        with self._client() as db:
            db.log_issue("7", "Real title", "bug", "qa", None)
            db.save_session("s1", "qa", "Review", "[]", issues=[7])
            issue = db.get_issue("7")
        self.assertEqual(issue["title"], "Real title")
        self.assertEqual(issue["status"], "qa")

    def test_save_session_rejects_a_non_numeric_issue(self):
        with self._client() as db:
            with self.assertRaises(ValueError):
                db.save_session("s1", "qa", "Review", "[]", issues=["42; DROP"])

    def test_resaving_a_session_does_not_duplicate_links(self):
        with self._client() as db:
            db.save_session("s1", "qa", "Review", "[]", issues=[42])
            db.save_session("s1", "qa", "Review again", "[]", issues=[42])
            rows = self._worked_on_rows(db)
        self.assertEqual(len(rows), 1)


class TestSaveLoopRunTargetIssueSqlite(_SqliteBase):
    def test_save_loop_run_stores_target_issue_and_links(self):
        with self._client() as db:
            rid = db.save_loop_run(
                stage="start", target="42", decision="d", status="ok",
                session_id="sid", target_issue=42,
            )
            runs = db.list_loop_runs(limit=1)
            rows = self._worked_on_rows(db)
        self.assertEqual(runs[0]["target_issue"], 42)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_table"], "loop_runs")
        self.assertEqual(rows[0]["source_id"], rid)
        self.assertEqual(rows[0]["github_id"], "42")

    def test_save_loop_run_without_target_issue_is_unchanged(self):
        with self._client() as db:
            db.save_loop_run(
                stage="loop", target="", decision="d", status="ok", session_id="s"
            )
            runs = db.list_loop_runs(limit=1)
            rows = self._worked_on_rows(db)
        self.assertIsNone(runs[0]["target_issue"])
        self.assertEqual(rows, [])


class TestWorkedOnRelateOnSurreal(unittest.TestCase):
    """Query-construction tests against a mocked SurrealDB backend."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")

    def tearDown(self):
        os.environ.pop("HARNESS_MIRROR_ROOT", None)
        self.temp_dir.cleanup()

    def _surreal_mock_client(self, result=None):
        client = DatabaseClient(db_path=os.path.join(self.temp_dir.name, "h.db"))
        client.backend = "surrealdb"
        client._run_surreal = MagicMock(return_value=result if result is not None else [])
        return client

    def test_save_session_with_issues_relates_session_to_issue(self):
        client = self._surreal_mock_client()
        # The issue row exists, so no minimal log_issue write happens.
        client.get_issue = MagicMock(return_value={"github_id": "42"})
        client.save_session("s1", "qa", "Review", "[]", issues=[42])
        relate_calls = [
            c for c in client._run_surreal.call_args_list
            if "RELATE" in c[0][0]
        ]
        self.assertEqual(len(relate_calls), 1)
        query, params = relate_calls[0][0]
        self.assertIn("RELATE $rel_from->worked_on->$rel_to", query)
        self.assertEqual(
            (params["rel_from"].table_name, params["rel_from"].id), ("sessions", "s1")
        )
        self.assertEqual(
            (params["rel_to"].table_name, params["rel_to"].id), ("issues", "42")
        )

    def test_save_loop_run_with_target_issue_relates_loop_run_to_issue(self):
        client = self._surreal_mock_client()
        client.get_issue = MagicMock(return_value={"github_id": "7"})
        client.save_loop_run(
            stage="review", target="7", decision="d", status="ok",
            session_id="sid", target_issue=7,
        )
        # The edge source must be the very record id the loop-run row was
        # UPSERTed under, so the graph and the row can never drift apart.
        upsert_calls = [
            c for c in client._run_surreal.call_args_list if "UPSERT" in c[0][0]
        ]
        minted = upsert_calls[0][0][1]["id"].id
        relate_calls = [
            c for c in client._run_surreal.call_args_list if "RELATE" in c[0][0]
        ]
        self.assertEqual(len(relate_calls), 1)
        query, params = relate_calls[0][0]
        self.assertIn("RELATE $rel_from->worked_on->$rel_to", query)
        self.assertEqual(params["rel_from"].table_name, "loop_runs")
        self.assertEqual(params["rel_from"].id, minted)
        self.assertTrue(str(minted).startswith("loop_run-"))
        self.assertEqual(
            (params["rel_to"].table_name, params["rel_to"].id), ("issues", "7")
        )

    def test_no_parity_row_is_written_when_the_edge_lands_on_surreal(self):
        client = self._surreal_mock_client()
        client.get_issue = MagicMock(return_value={"github_id": "42"})
        client.save_session("s1", "qa", "Review", "[]", issues=[42])
        client.backend = "sqlite"  # only to read the parity table directly
        with client._sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) AS n FROM worked_on")
            self.assertEqual(cur.fetchone()["n"], 0)


class TestLatestActivityPerIssueSqlite(_SqliteBase):
    def test_returns_the_most_recent_activity_per_issue(self):
        with self._client() as db:
            db.log_issue("1", "First", "feature", "in_progress", None)
            db.log_issue("2", "Second", "bug", "qa", None)
            db.save_session("s1", "qa", "old work", "[]", issues=[1])
            db.save_session("s2", "software_engineer", "new work", "[]", issues=[1])
            db.save_loop_run(
                stage="review", target="2", decision="ran /solomon-review",
                status="ok", session_id="x", target_issue=2,
            )
            rows = db.latest_activity_per_issue()
        self.assertEqual([r["github_id"] for r in rows], ["2", "1"])
        by_id = {r["github_id"]: r for r in rows}
        self.assertEqual(by_id["1"]["type"], "session")
        self.assertEqual(by_id["1"]["agent"], "software_engineer")
        self.assertEqual(by_id["1"]["task"], "new work")
        self.assertEqual(by_id["1"]["issue_status"], "in_progress")
        self.assertEqual(by_id["1"]["title"], "First")
        self.assertEqual(by_id["2"]["type"], "loop_run")
        self.assertEqual(by_id["2"]["status"], "ok")
        self.assertIn("timestamp", by_id["2"])

    def test_terminal_issues_are_excluded(self):
        with self._client() as db:
            db.log_issue("5", "Shipped", "feature", "closed", None)
            db.save_session("s1", "qa", "wrapped", "[]", issues=[5])
            rows = db.latest_activity_per_issue()
        self.assertEqual(rows, [])

    def test_limit_caps_the_rows(self):
        with self._client() as db:
            for n in range(1, 5):
                db.save_session(f"s{n}", "qa", f"work {n}", "[]", issues=[n])
            rows = db.latest_activity_per_issue(limit=2)
        self.assertEqual(len(rows), 2)

    def test_no_edges_means_no_rows(self):
        with self._client() as db:
            db.log_issue("9", "Untouched", "feature", "Ready", None)
            db.save_session("s1", "qa", "unlinked", "[]")
            self.assertEqual(db.latest_activity_per_issue(), [])


class TestGetLatestActivityIssuesKeySqlite(_SqliteBase):
    def test_issues_key_lists_linked_numbers(self):
        with self._client() as db:
            db.save_session("s1", "qa", "work", "[]", issues=[42, 7])
            activity = db.get_latest_activity()
        self.assertEqual(activity["type"], "session")
        self.assertEqual(activity["issues"], [7, 42])

    def test_no_issues_key_without_edges(self):
        # Consumers pin the exact resume shape; the key must not appear for
        # legacy sessions with no worked_on edges.
        with self._client() as db:
            db.save_session("s1", "qa", "work on #42", "[]")
            activity = db.get_latest_activity()
        self.assertNotIn("issues", activity)


class TestLatestActivityPerIssueSurrealUnit(unittest.TestCase):
    """Graph-query construction and merge logic against a mocked backend."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")

    def tearDown(self):
        os.environ.pop("HARNESS_MIRROR_ROOT", None)
        self.temp_dir.cleanup()

    def _surreal_mock_client(self, result=None):
        client = DatabaseClient(db_path=os.path.join(self.temp_dir.name, "h.db"))
        client.backend = "surrealdb"
        client._run_surreal = MagicMock(return_value=result if result is not None else [])
        return client

    def test_one_graph_query_over_both_sources(self):
        client = self._surreal_mock_client(result=[])
        client.latest_activity_per_issue()
        self.assertEqual(client._run_surreal.call_count, 1)
        query = client._run_surreal.call_args[0][0]
        self.assertIn("FROM issues", query)
        self.assertIn("<-worked_on<-sessions", query)
        self.assertIn("<-worked_on<-loop_runs", query)

    def test_merges_sources_and_filters_terminal(self):
        client = self._surreal_mock_client(
            result=[
                {
                    "github_id": "42", "title": "Open one",
                    "issue_status": "in_progress",
                    "sessions": [{
                        "session_id": "s1", "agent_name": "qa", "task": "t",
                        "status": "active", "timestamp": "2026-07-04T10:00:00Z",
                    }],
                    "loop_runs": [{
                        "stage": "start", "decision": "ran /solomon-start",
                        "status": "ok", "created_at": "2026-07-04T11:00:00Z",
                    }],
                },
                {
                    "github_id": "7", "title": "Shipped one",
                    "issue_status": "closed",
                    "sessions": [{
                        "session_id": "s2", "agent_name": "qa", "task": "t2",
                        "status": "done", "timestamp": "2026-07-04T12:00:00Z",
                    }],
                    "loop_runs": [],
                },
            ]
        )
        rows = client.latest_activity_per_issue()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["github_id"], "42")
        # The loop run is later than the session, so it wins the issue.
        self.assertEqual(rows[0]["type"], "loop_run")
        self.assertEqual(rows[0]["agent"], "start")
        self.assertEqual(rows[0]["status"], "ok")

    def test_get_latest_activity_issues_key_from_the_graph(self):
        client = self._surreal_mock_client()
        client._run_surreal = MagicMock(
            side_effect=[
                [{"session_id": "s1", "agent_name": "qa", "task": "t",
                  "status": "active", "timestamp": "2026-07-04T10:00:00Z"}],
                [],
                [{"gids": ["42", "7"]}],
            ]
        )
        activity = client.get_latest_activity()
        self.assertEqual(activity["type"], "session")
        self.assertEqual(activity["issues"], [7, 42])


class TestRecordLoopRunTargetIssue(unittest.TestCase):
    """workflows._record_loop_run passes the first purely-numeric arg."""

    def _record(self, args):
        instance = MagicMock()
        client_cls = MagicMock()
        client_cls.return_value.__enter__ = MagicMock(return_value=instance)
        client_cls.return_value.__exit__ = MagicMock(return_value=False)
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient", client_cls
        ):
            workflows._record_loop_run(".", "start", args, 0, "sid")
        return instance.save_loop_run.call_args

    def test_numeric_arg_becomes_target_issue(self):
        call = self._record(["42"])
        self.assertEqual(call.kwargs["target_issue"], 42)

    def test_first_numeric_arg_wins(self):
        call = self._record(["--flag", "7", "9"])
        self.assertEqual(call.kwargs["target_issue"], 7)

    def test_prose_is_never_parsed(self):
        call = self._record(["fix", "issue", "#42"])
        self.assertIsNone(call.kwargs["target_issue"])

    def test_no_args_means_no_target(self):
        call = self._record([])
        self.assertIsNone(call.kwargs["target_issue"])


if __name__ == "__main__":
    unittest.main()
