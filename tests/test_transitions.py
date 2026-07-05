"""First-class issue status transitions (ADR-0016, issue #166, finding F4).

A transitions row {issue, from_status, to_status, entered_at, actor} written at
the github.record_transition seam alongside the legacy board_history:* JSON
blob (expand/contract: the legacy write is kept for one release). The table is
typed on SurrealDB (issue record<issues>, entered_at datetime, composite
index), has a SQLite parity table so the fallback still records transitions,
and the cockpit read side prefers it per issue, falling back to the legacy
keys. The naive-local-clock timestamps become UTC.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness import github  # noqa: E402
from solomon_harness.cockpit_read import _load_board_histories  # noqa: E402
from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import FakeSurreal
except ImportError:  # pragma: no cover - depends on the discovery entry point
    from test_database_client_resilience import FakeSurreal  # type: ignore[no-redef]


class TestTransitionsSchema(unittest.TestCase):
    def test_transitions_ddl_statements_are_present_and_single(self):
        statements = DatabaseClient._SURREAL_SCHEMA_STATEMENTS
        expected_fragments = (
            "DEFINE TABLE IF NOT EXISTS transitions SCHEMALESS",
            "DEFINE FIELD IF NOT EXISTS issue ON transitions TYPE record<issues>",
            "DEFINE FIELD IF NOT EXISTS entered_at ON transitions TYPE datetime",
            "DEFINE INDEX IF NOT EXISTS transitions_issue_entered "
            "ON transitions FIELDS issue, entered_at",
        )
        for fragment in expected_fragments:
            matches = [s for s in statements if fragment in s]
            self.assertEqual(len(matches), 1, fragment)
            # One statement per list entry: the bootstrap invariant.
            self.assertEqual(matches[0].count(";"), 1, matches[0])


class TestRecordStatusTransitionSqlite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "harness.db")

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self):
        return DatabaseClient(db_path=self.db_path)

    def test_returns_minted_id_and_persists_normalized_utc_row(self):
        with self._client() as db:
            record_id = db.record_status_transition("42", "Ready", "In Progress", actor="alice")
            rows = db.get_status_transitions(["42"])["42"]
        self.assertIsNotNone(record_id)
        self.assertTrue(str(record_id).startswith("transition-"), record_id)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # Statuses are normalized to the canonical vocabulary on write.
        self.assertEqual(row["from_status"], "Ready")
        self.assertEqual(row["to_status"], "in_progress")
        self.assertEqual(row["actor"], "alice")
        # entered_at is UTC, not the naive local clock (finding F4).
        self.assertIn("+00:00", row["entered_at"])

    def test_bulk_read_groups_ascending_and_omits_absent_ids(self):
        with self._client() as db:
            db.record_status_transition("7", None, "In Progress")
            db.record_status_transition("7", "In Progress", "Done")
            db.record_status_transition("9", None, "Ready")
            grouped = db.get_status_transitions(["7", "9", "404"])
        self.assertEqual(set(grouped), {"7", "9"})
        seven = grouped["7"]
        self.assertEqual([r["to_status"] for r in seven], ["in_progress", "closed"])
        self.assertLessEqual(seven[0]["entered_at"], seven[1]["entered_at"])
        self.assertIsNone(seven[0]["from_status"])

    def test_empty_id_set_reads_nothing(self):
        with self._client() as db:
            self.assertEqual(db.get_status_transitions([]), {})


class TestRecordStatusTransitionSurreal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, fake):
        client = DatabaseClient(db_path=os.path.join(self.tmp.name, "harness.db"))
        client.backend = "surrealdb"
        client.db = fake
        return client

    def test_write_links_the_issue_record_and_stamps_server_time(self):
        fake = FakeSurreal(result=[[{"id": "transitions:t1"}]])
        client = self._client(fake)

        client.record_status_transition("42", "Ready", "Code Review", actor="bob")

        query, params = fake.calls[0]
        self.assertIn("time::now()", query)
        self.assertEqual(params["issue"].table_name, "issues")
        self.assertEqual(params["issue"].id, "42")
        self.assertEqual(params["github_id"], "42")
        self.assertEqual(params["to_status"], "code_review")
        self.assertEqual(params["actor"], "bob")

    def test_bulk_read_is_one_query_with_bound_ids(self):
        fake = FakeSurreal(
            result=[[
                {"github_id": "7", "from_status": None, "to_status": "in_progress",
                 "entered_at": "2026-07-01T00:00:00+00:00", "actor": None},
            ]]
        )
        client = self._client(fake)

        grouped = client.get_status_transitions(["7", "9"])

        self.assertEqual(len(fake.calls), 1)
        query, params = fake.calls[0]
        self.assertIn("$ids", query)
        self.assertEqual(params["ids"], ["7", "9"])
        self.assertEqual(grouped["7"][0]["to_status"], "in_progress")


class TestGithubRecordTransitionSeam(unittest.TestCase):
    def test_writes_legacy_history_and_transitions_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.getcwd", return_value=tmp), patch.dict(
                os.environ, {"GITHUB_ACTOR": "carol"}
            ):
                github.record_transition(7, "In Progress")
                github.record_transition(7, "Code Review")
                with DatabaseClient(harness_dir=tmp) as db:
                    raw = db.get_memory("board_history:7")
                    rows = db.get_status_transitions(["7"])["7"]

        # The legacy write is kept for one release (expand/contract), now UTC.
        history = json.loads(raw)
        self.assertEqual([h["column"] for h in history], ["In Progress", "Code Review"])
        self.assertTrue(all(h["entered_at"].endswith("+00:00") for h in history))

        # The first-class rows chain from_status from the previous column.
        self.assertEqual([r["to_status"] for r in rows], ["in_progress", "code_review"])
        self.assertIsNone(rows[0]["from_status"])
        self.assertEqual(rows[1]["from_status"], "in_progress")
        self.assertEqual(rows[0]["actor"], "carol")

    def test_never_raises_on_failure(self):
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            side_effect=RuntimeError,
        ):
            github.record_transition(1, "Done")


class _FakeCockpitClient:
    """A read-port fake exposing exactly what _load_board_histories touches."""

    def __init__(self, transitions=None, legacy=None, transitions_error=False):
        self.transitions = transitions or {}
        self.legacy = legacy or {}
        self.transitions_error = transitions_error
        self.bulk_requests = []

    def get_status_transitions(self, github_ids):
        if self.transitions_error:
            raise RuntimeError("transitions read failed")
        return {gid: self.transitions[gid] for gid in github_ids if gid in self.transitions}

    def get_memory_bulk(self, keys):
        self.bulk_requests.append(list(keys))
        return {k: self.legacy[k] for k in keys if k in self.legacy}


class TestCockpitPrefersTransitions(unittest.TestCase):
    def test_transitions_rows_win_per_issue_with_legacy_fallback(self):
        client = _FakeCockpitClient(
            transitions={
                "1": [
                    {"from_status": None, "to_status": "closed",
                     "entered_at": "2026-07-02T10:00:00+00:00", "actor": None},
                ]
            },
            legacy={
                "board_history:2": json.dumps(
                    [{"column": "Done", "entered_at": "2026-07-01T09:00:00"}]
                ),
            },
        )

        histories = _load_board_histories(client, ["1", "2"])

        # Issue 1 comes from the transitions table, adapted to the history shape.
        self.assertEqual(histories["1"], [
            {"column": "closed", "entered_at": "2026-07-02T10:00:00+00:00"},
        ])
        # Issue 2 falls back to the legacy key.
        self.assertEqual(histories["2"][0]["column"], "Done")
        # Only the uncovered id was read from the legacy store.
        self.assertEqual(client.bulk_requests, [["board_history:2"]])

    def test_transitions_read_failure_degrades_to_legacy(self):
        client = _FakeCockpitClient(
            transitions_error=True,
            legacy={
                "board_history:1": json.dumps(
                    [{"column": "Done", "entered_at": "2026-07-01T09:00:00"}]
                ),
            },
        )
        histories = _load_board_histories(client, ["1"])
        self.assertEqual(histories["1"][0]["column"], "Done")

    def test_no_reads_at_all_yields_empty(self):
        self.assertEqual(_load_board_histories(_FakeCockpitClient(), []), {})


if __name__ == "__main__":
    unittest.main()
