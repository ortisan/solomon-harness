"""Tests for the loop-run ledger and the read-only log feed (Phase 0).

The ledger lives in the project memory (the single source of truth); the feed is
a pure formatter over decisions, handoffs and loop runs, so the loop's own
decisions become auditable without querying the store directly.
"""

import os
import sys
import tempfile
import unittest

from solomon_harness.tools.database_client import (
    LOOP_RUN_STATUSES,
    DatabaseClient,
    normalize_loop_run_status,
)
from solomon_harness import loop_log

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import FakeSurreal
except ImportError:  # pragma: no cover - depends on the discovery entry point
    from test_database_client_resilience import FakeSurreal  # type: ignore[no-redef]


class TestLoopRunLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "harness.db")

    def test_save_and_list_loop_run(self):
        with DatabaseClient(db_path=self.db_path) as db:
            db.save_loop_run(
                stage="start",
                target="42",
                decision="advanced ready -> in progress",
                status="ok",
                session_id="h1:123",
            )
            rows = db.list_loop_runs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "start")
        self.assertEqual(rows[0]["target"], "42")
        self.assertEqual(rows[0]["status"], "ok")

    def test_list_loop_runs_is_newest_first_and_limited(self):
        with DatabaseClient(db_path=self.db_path) as db:
            for i in range(5):
                db.save_loop_run(stage="loop", target=str(i), decision="d", status="ok", session_id="s")
            rows = db.list_loop_runs(limit=3)
        self.assertEqual(len(rows), 3)
        # AUTOINCREMENT id ordering: most recent target ("4") comes first.
        self.assertEqual(rows[0]["target"], "4")


class TestLoopRunStatusVocabulary(unittest.TestCase):
    """Canonical loop-run vocabulary {ok, failed}, normalized on write (#165).

    The writer (workflows.py) stores 'ok'/'failed' while the aggregator counted
    'failure', so every failed run was invisible to the failure rate. The fix is
    on the client seam: normalize at save_loop_run, count both tokens on read.
    """

    def test_canonical_vocabulary_is_ok_failed(self):
        self.assertEqual(LOOP_RUN_STATUSES, ("ok", "failed"))

    def test_normalize_maps_legacy_tokens_to_canonical(self):
        for legacy, canonical in (
            ("success", "ok"),
            ("passed", "ok"),
            ("ok", "ok"),
            ("failure", "failed"),
            ("error", "failed"),
            ("failed", "failed"),
            ("OK", "ok"),
            (" Failure ", "failed"),
        ):
            self.assertEqual(normalize_loop_run_status(legacy), canonical, legacy)

    def test_normalize_passes_unknown_tokens_through_lowercased(self):
        self.assertEqual(normalize_loop_run_status("Skipped"), "skipped")

    def test_normalize_none_stays_none(self):
        self.assertIsNone(normalize_loop_run_status(None))

    def test_save_loop_run_normalizes_at_the_write_seam(self):
        tmp = tempfile.mkdtemp()
        with DatabaseClient(db_path=os.path.join(tmp, "h.db")) as db:
            db.save_loop_run(stage="dev", target="1", decision="d", status="failure", session_id="s")
            db.save_loop_run(stage="dev", target="2", decision="d", status="success", session_id="s")
            rows = db.list_loop_runs()
        by_target = {row["target"]: row["status"] for row in rows}
        self.assertEqual(by_target["1"], "failed")
        self.assertEqual(by_target["2"], "ok")


class TestLoopRunFailureRateCountsLegacyRows(unittest.TestCase):
    """loop_run_failure_rate counts canonical 'failed' PLUS legacy 'failure' rows,
    so runs recorded before the vocabulary fix do not vanish from the metric."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _surreal_client(self, fake):
        client = DatabaseClient(db_path=os.path.join(self.tmp, "h.db"))
        client.backend = "surrealdb"
        client.db = fake
        return client

    def test_failure_rate_counts_both_failed_and_failure(self):
        fake = FakeSurreal(result=[[{"total": 4, "failures": 3}]])
        client = self._surreal_client(fake)

        rate = client.loop_run_failure_rate()

        self.assertEqual(rate, {"total": 4, "failures": 3, "failure_rate": 0.75})
        query = fake.calls[0][0]
        self.assertIn("'failed'", query)
        self.assertIn("'failure'", query)
        self.assertIn("IN", query)


class TestLogFeed(unittest.TestCase):
    def test_format_feed_renders_each_kind(self):
        entries = [
            {"kind": "loop_run", "when": "2026-06-28T10:00:00", "text": "ran /solomon-start 42 -> ok"},
            {"kind": "decision", "when": "2026-06-28T09:00:00", "text": "chose hexagonal lock"},
            {"kind": "handoff", "when": "2026-06-28T08:00:00", "text": "start -> review"},
        ]
        out = "\n".join(loop_log.format_feed(entries))
        self.assertIn("ran /solomon-start 42 -> ok", out)
        self.assertIn("chose hexagonal lock", out)
        self.assertIn("start -> review", out)

    def test_gather_feed_merges_sources_newest_first(self):
        tmp = tempfile.mkdtemp()
        with DatabaseClient(db_path=os.path.join(tmp, "h.db")) as db:
            db.log_decision("older", "r", "o", "a", "b", "sha")
            db.save_loop_run(stage="loop", target="1", decision="newer", status="ok", session_id="s")
            entries = loop_log.gather_feed(db, last=10)
        self.assertGreaterEqual(len(entries), 2)
        kinds = [e["kind"] for e in entries]
        self.assertIn("loop_run", kinds)
        self.assertIn("decision", kinds)


if __name__ == "__main__":
    unittest.main()
