"""Typed states for the stateful memory kinds (ADR-0016, issue #166).

Canonical vocabularies for handoffs, sessions, and milestones, normalized at
the DatabaseClient write seam like the issue vocabulary (ADR-0006); targeted
DEFINE FIELD ASSERT statements on SurrealDB (one statement per query() call,
the hard-won bootstrap invariant); the handoff lifecycle (update_handoff_status
and the persisted summary); and replay-side normalization so a legacy pending
mirror can never trip an assert.
"""

import os
import sqlite3
import sys
import tempfile
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    HANDOFF_STATUSES,
    MILESTONE_STATES,
    SESSION_STATUSES,
    DatabaseClient,
    normalize_handoff_status,
    normalize_milestone_state,
    normalize_session_status,
    normalize_status,
)

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import FakeSurreal
except ImportError:  # pragma: no cover - depends on the discovery entry point
    from test_database_client_resilience import FakeSurreal  # type: ignore[no-redef]


class TestVocabulariesAndNormalizers(unittest.TestCase):
    def test_handoff_vocabulary(self):
        self.assertEqual(HANDOFF_STATUSES, ("open", "accepted", "done"))

    def test_session_vocabulary(self):
        self.assertEqual(SESSION_STATUSES, ("active", "done"))

    def test_milestone_vocabulary(self):
        self.assertEqual(MILESTONE_STATES, ("open", "closed"))

    def test_normalize_handoff_status_maps_aliases(self):
        for legacy, canonical in (
            ("ready", "open"),
            ("pending", "open"),
            ("approved", "accepted"),
            ("completed", "done"),
            ("closed", "done"),
            ("open", "open"),
            ("accepted", "accepted"),
            ("done", "done"),
            ("Ready", "open"),
        ):
            self.assertEqual(normalize_handoff_status(legacy), canonical, legacy)

    def test_normalize_session_status_maps_aliases(self):
        for legacy, canonical in (
            ("active", "active"),
            ("completed", "done"),
            ("closed", "done"),
            ("finished", "done"),
            ("Done", "done"),
        ):
            self.assertEqual(normalize_session_status(legacy), canonical, legacy)

    def test_normalize_milestone_state_maps_aliases(self):
        for legacy, canonical in (
            ("active", "open"),
            ("pending", "open"),
            ("complete", "closed"),
            ("completed", "closed"),
            ("done", "closed"),
            ("open", "open"),
            ("closed", "closed"),
        ):
            self.assertEqual(normalize_milestone_state(legacy), canonical, legacy)

    def test_normalizers_pass_none_through(self):
        self.assertIsNone(normalize_handoff_status(None))
        self.assertIsNone(normalize_session_status(None))
        self.assertIsNone(normalize_milestone_state(None))

    def test_normalizers_pass_unknown_tokens_through_lowercased(self):
        self.assertEqual(normalize_handoff_status("Weird"), "weird")
        self.assertEqual(normalize_session_status("Weird"), "weird")
        self.assertEqual(normalize_milestone_state("Weird"), "weird")

    def test_issue_status_casing_aliases_collapse(self):
        # ADR-0016 hardening of the ADR-0006 vocabulary: the display columns and
        # the legacy literal open collapse casing so the store never holds two
        # rows differing only by case.
        self.assertEqual(normalize_status("backlog"), "Backlog")
        self.assertEqual(normalize_status("ideas"), "Ideas")
        self.assertEqual(normalize_status("ready"), "Ready")
        self.assertEqual(normalize_status("Open"), "open")


class SqliteClientBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "harness.db")

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self):
        return DatabaseClient(db_path=self.db_path)


class TestWriteSeamNormalization(SqliteClientBase):
    def test_log_handoff_normalizes_and_persists_summary(self):
        with self._client() as db:
            handoff_id = db.log_handoff(
                "dev", "qa", "plan", "/p.md", "pending", summary="implemented the parser"
            )
            row = db.get_handoff(handoff_id)
        assert row is not None
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["summary"], "implemented the parser")

    def test_log_handoff_summary_defaults_empty(self):
        with self._client() as db:
            handoff_id = db.log_handoff("dev", "qa", "plan", "/p.md", "open")
            row = db.get_handoff(handoff_id)
        assert row is not None
        self.assertEqual(row["summary"], "")

    def test_save_session_persists_status_and_defaults_active(self):
        with self._client() as db:
            db.save_session("s1", "dev", "task", [])
            db.save_session("s2", "dev", "task", [], status="Completed")
            default_row = db.get_session("s1")
            done_row = db.get_session("s2")
        assert default_row is not None and done_row is not None
        self.assertEqual(default_row["status"], "active")
        self.assertEqual(done_row["status"], "done")

    def test_create_milestone_normalizes_state(self):
        with self._client() as db:
            db.create_milestone("m", "d", "2026-07-01", "active")
            rows = db.list_milestones()
        self.assertEqual(rows[0]["state"], "open")


class TestGetLatestActivityStatus(SqliteClientBase):
    def test_session_status_is_read_from_the_row(self):
        with self._client() as db:
            db.save_session("s1", "dev", "task", [], status="done")
            activity = db.get_latest_activity()
        assert activity is not None
        self.assertEqual(activity["type"], "session")
        self.assertEqual(activity["status"], "done")

    def test_legacy_session_row_without_status_defaults_active(self):
        with self._client() as db:
            db.save_session("s1", "dev", "task", [])
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE sessions SET status = NULL")
                conn.commit()
            activity = db.get_latest_activity()
        assert activity is not None
        self.assertEqual(activity["status"], "active")

    def test_handoff_activity_surfaces_summary(self):
        with self._client() as db:
            db.log_handoff("dev", "qa", "plan", "/p.md", "open", summary="what was done")
            activity = db.get_latest_activity()
        assert activity is not None
        self.assertEqual(activity["type"], "handoff")
        self.assertEqual(activity["summary"], "what was done")


class TestUpdateHandoffStatus(SqliteClientBase):
    def test_update_handoff_status_moves_the_lifecycle(self):
        with self._client() as db:
            handoff_id = db.log_handoff("dev", "qa", "plan", "/p.md", "open", summary="s")
            result = db.update_handoff_status(handoff_id, "accepted")
            row = db.get_handoff(handoff_id)
        assert row is not None
        self.assertIsNotNone(result)
        self.assertEqual(row["status"], "accepted")
        # The rest of the row is untouched.
        self.assertEqual(row["sender"], "dev")
        self.assertEqual(row["summary"], "s")

    def test_update_handoff_status_normalizes(self):
        with self._client() as db:
            handoff_id = db.log_handoff("dev", "qa", "plan", "/p.md", "open")
            db.update_handoff_status(handoff_id, "Completed")
            row = db.get_handoff(handoff_id)
        assert row is not None
        self.assertEqual(row["status"], "done")

    def test_update_missing_handoff_returns_none(self):
        with self._client() as db:
            self.assertIsNone(db.update_handoff_status(99999, "done"))


class TestUpdateHandoffStatusSurreal(unittest.TestCase):
    """The SurrealDB path issues a targeted UPDATE and re-mirrors the merged row."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "harness.db")
        self.mirror_root = os.path.join(self.tmp.name, "mirror")

    def tearDown(self):
        self.tmp.cleanup()

    def test_surreal_update_targets_the_record_and_sets_canonical_status(self):
        row = {
            "id": "handoffs:⟨handoff-x⟩",
            "sender": "dev",
            "recipient": "qa",
            "contract_type": "plan",
            "contract_path": "/p.md",
            "status": "open",
            "summary": "s",
        }

        def respond(query, params=None):
            if query.strip().startswith("SELECT"):
                return [[row]]
            return [[{**row, "status": "accepted"}]]

        fake = FakeSurreal(result=respond)
        client = DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()
        client.backend = "surrealdb"
        client.db = fake

        client.update_handoff_status("handoffs:⟨handoff-x⟩", "approved")

        updates = [(q, p) for q, p in fake.calls if q.strip().startswith("UPDATE")]
        self.assertEqual(len(updates), 1)
        query, params = updates[0]
        self.assertIn("SET status = $status", query)
        self.assertEqual(params["status"], "accepted")
        # The RecordID targets the bare binary key, not the ⟨⟩-delimited display form.
        self.assertEqual(params["id"].table_name, "handoffs")
        self.assertEqual(params["id"].id, "handoff-x")
        # The mirror carries the merged fields under the bare record key.
        path = os.path.join(self.mirror_root, "handoff", "handoff-x.md")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('"status": "accepted"', text)
        self.assertIn('"sender": "dev"', text)
        self.assertIn("synced: true", text)


class TestSchemaAsserts(unittest.TestCase):
    """Targeted DEFINE FIELD ASSERT DDL: present, canonical, and one statement
    per list entry so the one-statement-per-query() bootstrap invariant holds."""

    STATEFUL_FIELDS = (
        ("status", "issues", ("'in_progress'", "'code_review'", "'qa'", "'closed'")),
        ("status", "handoffs", ("'open'", "'accepted'", "'done'")),
        ("status", "sessions", ("'active'", "'done'")),
        ("status", "loop_runs", ("'ok'", "'failed'")),
        ("state", "milestones", ("'open'", "'closed'")),
    )

    def _statement_for(self, field, table):
        needle = f"DEFINE FIELD IF NOT EXISTS {field} ON {table} "
        matches = [s for s in DatabaseClient._SURREAL_SCHEMA_STATEMENTS if needle in s]
        self.assertEqual(len(matches), 1, f"expected one assert statement for {table}.{field}")
        return matches[0]

    def test_every_stateful_field_has_a_targeted_assert(self):
        for field, table, tokens in self.STATEFUL_FIELDS:
            statement = self._statement_for(field, table)
            self.assertIn("ASSERT", statement)
            # NONE stays allowed so rows that never carried the field are untouched.
            self.assertIn("$value = NONE", statement)
            for token in tokens:
                self.assertIn(token, statement, f"{table}.{field} must allow {token}")

    def test_issue_assert_keeps_legacy_literals_writable(self):
        # Replays and legacy flows still write open/done/Done; the assert must
        # not reject them (expand/contract, ADR-0006 read tolerance).
        statement = self._statement_for("status", "issues")
        for token in ("'open'", "'done'", "'Done'", "'Ideas'", "'Backlog'", "'Ready'"):
            self.assertIn(token, statement)

    def test_each_schema_statement_is_a_single_statement(self):
        # The surrealdb SDK only surfaces the FIRST statement's result per
        # .query() call, so every list entry must hold exactly one statement.
        for statement in DatabaseClient._SURREAL_SCHEMA_STATEMENTS:
            self.assertEqual(statement.count(";"), 1, statement)
            self.assertTrue(statement.rstrip().endswith(";"), statement)


class TestReplayNormalizesStatuses(unittest.TestCase):
    """Reconcile replays route each kind's status through its normalizer, so a
    legacy pending mirror (pending/failure/active) can never trip an assert."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "harness.db")
        self.mirror_root = os.path.join(self.tmp.name, "mirror")

    def tearDown(self):
        self.tmp.cleanup()

    def _client_with(self, fake):
        client = DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()
        client.backend = "surrealdb"
        client.db = fake
        return client

    def _pend(self, client, kind, record_id, fields):
        client._mirror_write(
            kind, record_id, fields, synced=False, created_at="2026-07-01T00:00:00+00:00"
        )

    def test_replay_normalizes_handoff_loop_run_and_milestone_tokens(self):
        fake = FakeSurreal(result=[])
        client = self._client_with(fake)
        self._pend(
            client,
            "handoff",
            "handoff-1",
            {"sender": "a", "recipient": "b", "contract_type": "plan",
             "contract_path": "/p", "status": "pending"},
        )
        self._pend(
            client,
            "loop_run",
            "loop_run-1",
            {"stage": "dev", "target": "1", "decision": "d",
             "status": "failure", "session_id": "s"},
        )
        self._pend(
            client,
            "milestone",
            "milestone-1",
            {"title": "m", "description": "d", "due_date": "2026-07-01", "state": "active"},
        )

        result = client.reconcile()

        self.assertEqual(result, {"synced": 3, "remaining": 0})
        upserted = {p["id"].id: p["content"] for q, p in fake.calls if "UPSERT" in q}
        self.assertEqual(upserted["handoff-1"]["status"], "open")
        self.assertEqual(upserted["loop_run-1"]["status"], "failed")
        self.assertEqual(upserted["milestone-1"]["state"], "open")


class TestMcpToolRegistration(unittest.TestCase):
    def test_update_handoff_status_tool_is_registered(self):
        import asyncio
        from unittest.mock import patch

        try:
            import mcp  # noqa: F401
        except ImportError:  # pragma: no cover - mcp is a declared dependency
            self.skipTest("mcp package not installed")

        from solomon_harness import mcp_server

        real_isfile = os.path.isfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"SOLOMON_HARNESS_DIR": tmp}), patch(
                "os.path.isfile",
                side_effect=lambda p: False if "config.json" in str(p) else real_isfile(p),
            ):
                server = mcp_server.build_server()
            tools = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertIn("update_handoff_status", tools)


if __name__ == "__main__":
    unittest.main()
