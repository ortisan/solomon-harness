"""Closing the durability funnel: edges, metrics, and backend-invariant ids
(ADR-0016, findings F5/F7/F8, issue #166).

Graph edges and metric points now route through the _write_through mirror like
every other kind, so a write during a SurrealDB outage survives to reconcile:
an edge replays as an idempotent RELATE (check-before-create on its stamped
record_id), a metric replays as an UPSERT carrying its original time. On the
SQLite fallback every minted-id table stores the id in a record_id column and
every write method returns the minted id -- never lastrowid -- so an id means
the same thing on both backends.
"""

import glob
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import FakeSurreal
except ImportError:  # pragma: no cover - depends on the discovery entry point
    from test_database_client_resilience import FakeSurreal  # type: ignore[no-redef]


class FunnelTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "harness.db")
        self.mirror_root = os.path.join(self.tmp.name, "mirror")

    def tearDown(self):
        self.tmp.cleanup()

    def _configured_client(self, fake, connect=None):
        client = DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()  # SurrealDB is the configured primary
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


class TestRelateThroughTheFunnel(FunnelTestBase):
    def test_healthy_relate_mirrors_synced_true_and_stamps_record_id(self):
        fake = FakeSurreal(result=[[{"id": "blocks:x"}]])
        client = self._configured_client(fake)

        edge_id = client.relate("blocks", "issues:1", "issues:2", reason="dep")

        self.assertIsNotNone(edge_id)
        files = self._mirror_files("edge")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("synced: true", text)
        self.assertIn('"edge": "blocks"', text)
        relates = [(q, p) for q, p in fake.calls if q.startswith("RELATE")]
        self.assertEqual(len(relates), 1)
        query, params = relates[0]
        self.assertIn("record_id = $record_id", query)
        self.assertIn("reason = $reason", query)
        self.assertTrue(str(params["record_id"]).startswith("edge-"))

    def test_outage_relate_returns_minted_id_and_leaves_pending_mirror(self):
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            edge_id = client.relate("blocks", "issues:1", "issues:2")

        self.assertTrue(str(edge_id).startswith("edge-"), edge_id)
        files = self._mirror_files("edge")
        self.assertEqual(len(files), 1)
        self.assertIn("synced: false", self._read(files[0]))
        self.assertEqual(client.backend, "sqlite")

    def test_reconcile_replays_edge_as_idempotent_relate(self):
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)
        with redirect_stderr(io.StringIO()):
            edge_id = client.relate("blocks", "issues:1", "issues:2", reason="dep")

        # The primary recovers: the check finds nothing, so RELATE runs once.
        recovered = FakeSurreal(result=[])
        client.backend = "surrealdb"
        client.db = recovered

        result = client.reconcile()

        self.assertEqual(result, {"synced": 1, "remaining": 0})
        relates = [(q, p) for q, p in recovered.calls if q.startswith("RELATE")]
        self.assertEqual(len(relates), 1)
        query, params = relates[0]
        self.assertIn("->blocks->", query)
        self.assertEqual(params["record_id"], edge_id)
        self.assertEqual(params["reason"], "dep")
        self.assertEqual(params["rel_from"].table_name, "issues")
        self.assertEqual(params["rel_from"].id, "1")

        # A second reconcile finds the edge already present and does not RELATE.
        already = FakeSurreal(result=[[{"record_id": edge_id}]])
        client.db = already
        # Force the mirror pending again to prove the check-before-create guard.
        meta_path = self._mirror_files("edge")[0]
        text = self._read(meta_path).replace("synced: true", "synced: false")
        with open(meta_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        result2 = client.reconcile()
        self.assertEqual(result2, {"synced": 1, "remaining": 0})
        self.assertFalse([q for q, _ in already.calls if q.startswith("RELATE")])

    def test_pure_sqlite_config_still_raises_the_graph_guard(self):
        client = DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)
        with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
            client.relate("blocks", "issues:1", "issues:2")
        self.assertEqual(self._mirror_files("edge"), [])

    def test_reserved_edge_field_names_are_rejected(self):
        fake = FakeSurreal(result=[])
        client = self._configured_client(fake)
        for reserved in ("rel_from", "rel_to", "record_id", "id"):
            with self.assertRaises(ValueError):
                client.relate("blocks", "issues:1", "issues:2", **{reserved: "x"})


class TestRecordMetricThroughTheFunnel(FunnelTestBase):
    def test_healthy_metric_mirrors_synced_true(self):
        fake = FakeSurreal(result=[[{"id": "metrics:m1"}]])
        client = self._configured_client(fake)

        metric_id = client.record_metric("latency", 12.5, tags={"stage": "dev"})

        self.assertIsNotNone(metric_id)
        files = self._mirror_files("metric")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("synced: true", text)
        self.assertIn('"name": "latency"', text)
        upserts = [(q, p) for q, p in fake.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        import datetime as _dt

        self.assertIsInstance(upserts[0][1]["time"], _dt.datetime)

    def test_outage_metric_lands_in_sqlite_and_replays_with_original_time(self):
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            metric_id = client.record_metric(
                "latency", 1.5, at="2026-06-01T00:00:00+00:00"
            )

        self.assertTrue(str(metric_id).startswith("metric-"), metric_id)
        # The point is durable on the fallback (statistics survive an outage).
        rows = client.query_metric("latency")
        self.assertEqual([row["value"] for row in rows], [1.5])
        files = self._mirror_files("metric")
        self.assertIn("synced: false", self._read(files[0]))

        # Reconcile replays the UPSERT with the ORIGINAL time as a datetime.
        recovered = FakeSurreal(result=[])
        client.backend = "surrealdb"
        client.db = recovered
        result = client.reconcile()
        self.assertEqual(result, {"synced": 1, "remaining": 0})
        upserts = [(q, p) for q, p in recovered.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        content = upserts[0][1]["content"]
        import datetime as _dt

        self.assertIsInstance(content["time"], _dt.datetime)
        self.assertEqual(content["time"].isoformat(), "2026-06-01T00:00:00+00:00")

    def test_metric_returns_minted_id_on_sqlite(self):
        client = DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)
        metric_id = client.record_metric("latency", 2.0)
        self.assertTrue(str(metric_id).startswith("metric-"), metric_id)


class TestBackendInvariantRecordIds(FunnelTestBase):
    """F7: every minted-id write returns the minted id on SQLite too, stored in
    a record_id column, and the get-by-id paths accept it."""

    def _sqlite_client(self):
        return DatabaseClient(db_path=self.db_path, mirror_root=self.mirror_root)

    def test_every_minted_write_returns_its_minted_id(self):
        client = self._sqlite_client()
        checks = (
            (client.log_decision("t", "r", "o", "a", "b", "sha"), "decision-"),
            (client.create_milestone("m", "d", "2026-07-01", "open"), "milestone-"),
            (client.save_release("v1.0.0", tag="v1"), "release-"),
            (client.save_backtest("s", 1.0, 0.1, 1.2, "{}", "ds", "sha"), "backtest-"),
            (client.log_handoff("a", "b", "plan", "/p", "open"), "handoff-"),
            (
                client.save_loop_run(
                    stage="dev", target="1", decision="d", status="ok", session_id="s"
                ),
                "loop_run-",
            ),
        )
        for value, prefix in checks:
            self.assertTrue(str(value).startswith(prefix), (value, prefix))

    def test_minted_ids_round_trip_through_the_get_by_id_paths(self):
        client = self._sqlite_client()
        decision_id = client.log_decision("t", "r", "o", "a", "b", "sha")
        milestone_id = client.create_milestone("m", "d", "2026-07-01", "open")
        release_id = client.save_release("v1.0.0")
        backtest_id = client.save_backtest("s", 1.0, 0.1, 1.2, "{}", "ds", "sha")
        handoff_id = client.log_handoff("a", "b", "plan", "/p", "open")

        decision = client.get_decision(decision_id)
        milestone = client.get_milestone(milestone_id)
        release = client.get_release(release_id)
        backtest = client.get_backtest(backtest_id)
        handoff = client.get_handoff(handoff_id)
        assert decision and milestone and release and backtest and handoff
        self.assertEqual(decision["title"], "t")
        self.assertEqual(milestone["title"], "m")
        self.assertEqual(release["version"], "v1.0.0")
        self.assertEqual(backtest["strategy_name"], "s")
        self.assertEqual(handoff["sender"], "a")

    def test_surreal_style_table_key_spelling_is_accepted_on_sqlite(self):
        client = self._sqlite_client()
        decision_id = client.log_decision("t", "r", "o", "a", "b", "sha")
        spelled = f"decisions:⟨{decision_id}⟩"
        decision = client.get_decision(spelled)
        assert decision is not None
        self.assertEqual(decision["title"], "t")

    def test_legacy_integer_ids_still_resolve(self):
        client = self._sqlite_client()
        client.log_decision("t", "r", "o", "a", "b", "sha")  # ensures the table
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO decisions (title, rationale, outcome, author, branch, commit_sha)"
                " VALUES ('legacy', 'r', 'o', 'a', 'b', 's')"
            )
            legacy_id = cursor.lastrowid
            conn.commit()
        decision = client.get_decision(legacy_id)
        assert decision is not None
        self.assertEqual(decision["title"], "legacy")

    def test_update_handoff_status_works_with_the_minted_id(self):
        client = self._sqlite_client()
        handoff_id = client.log_handoff("a", "b", "plan", "/p", "open", summary="s")
        result = client.update_handoff_status(handoff_id, "done")
        self.assertIsNotNone(result)
        row = client.get_handoff(handoff_id)
        assert row is not None
        self.assertEqual(row["status"], "done")

    def test_minted_milestone_id_links_an_issue_without_fk_failure(self):
        # F7 consequence: issues.milestone_id now carries the minted milestone
        # record id, which the legacy FOREIGN KEY (targeting the integer rowid)
        # would reject. The FK is dropped: SurrealDB (the primary) never had
        # one, and the milestone linkage is soft by design (ADR-0016).
        client = self._sqlite_client()
        milestone_id = client.create_milestone("m", "d", "2026-07-01", "open")
        client.log_issue("gh-1", "t", "feature", "open", milestone_id)
        issue = client.get_issue("gh-1")
        assert issue is not None
        self.assertEqual(issue["milestone_id"], str(milestone_id))

    def test_pre_migration_fk_store_is_rebuilt_and_keeps_legacy_rows(self):
        # A store created before ADR-0016 carries the FK-bearing issues table.
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE milestones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    due_date TEXT,
                    state TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE issues (
                    github_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type_ TEXT,
                    status TEXT,
                    milestone_id TEXT,
                    assignee TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (milestone_id) REFERENCES milestones (id)
                );
                """
            )
            conn.execute(
                "INSERT INTO milestones (title, description, due_date, state)"
                " VALUES ('legacy', 'd', '2026-01-01', 'open')"
            )
            conn.execute(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id)"
                " VALUES ('gh-old', 'old', 'bug', 'open', '1')"
            )
            conn.commit()

        client = self._sqlite_client()  # opening rebuilds without the FK
        minted = client.create_milestone("new", "d", "2026-07-01", "open")
        client.log_issue("gh-new", "new", "feature", "open", minted)

        old_issue = client.get_issue("gh-old")
        new_issue = client.get_issue("gh-new")
        assert old_issue is not None and new_issue is not None
        self.assertEqual(old_issue["milestone_id"], "1")
        self.assertEqual(new_issue["milestone_id"], str(minted))

    def test_pre_migration_store_gains_record_id_additively(self):
        # A store created before ADR-0016: the decisions table has no record_id.
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    rationale TEXT,
                    outcome TEXT,
                    author TEXT,
                    branch TEXT,
                    commit_sha TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "INSERT INTO decisions (title, rationale, outcome, author, branch, commit_sha)"
                " VALUES ('old', 'r', 'o', 'a', 'b', 's')"
            )
            conn.commit()

        client = self._sqlite_client()  # opening migrates expand/contract
        new_id = client.log_decision("new", "r", "o", "a", "b", "s")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = {r["title"]: r["record_id"] for r in conn.execute(
                "SELECT title, record_id FROM decisions"
            )}
        self.assertIsNone(rows["old"])  # legacy rows keep a NULL record_id
        self.assertEqual(rows["new"], new_id)


if __name__ == "__main__":
    unittest.main()
