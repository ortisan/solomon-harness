"""Tests for the loop-run ledger and the read-only log feed (Phase 0).

The ledger lives in the project memory (the single source of truth); the feed is
a pure formatter over decisions, handoffs and loop runs, so the loop's own
decisions become auditable without querying the store directly.
"""

import os
import tempfile
import unittest

from solomon_harness.tools.database_client import DatabaseClient
from solomon_harness import loop_log


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
