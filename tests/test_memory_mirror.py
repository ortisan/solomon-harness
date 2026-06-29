"""Write-through markdown mirror + reconcile-on-recovery tests (issue #35).

These layer on the connection-resilience harness from #37: they reuse FakeSurreal
and ResilienceTestBase to drive the SurrealDB branch hermetically (no live backend,
no Docker), SQLite-isolate via a temp db_path, and point the mirror at a temp dir.
A client is marked as having SurrealDB configured as its primary (``_surreal_class``
set) so the synced/reconcile logic behaves like a real two-store client.
"""

import glob
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import (  # noqa: E402
        TRANSPORT_ERROR,
        FakeSurreal,
        ResilienceTestBase,
    )
except ImportError:  # pragma: no cover - depends on the discovery entry point
    # Same names as the try branch: with namespace packages mypy resolves both
    # module paths to one file and reports a redefinition, but only one branch
    # runs at import time.
    from test_database_client_resilience import (  # type: ignore[no-redef]  # noqa: E402
        TRANSPORT_ERROR,
        FakeSurreal,
        ResilienceTestBase,
    )


class MirrorTestBase(ResilienceTestBase):
    def setUp(self):
        super().setUp()
        self.mirror_root = os.path.join(self.temp_dir.name, "mirror")

    def _configured_client(self, fake, connect=None):
        """A SQLite-isolated client switched onto the SurrealDB branch and marked as
        having SurrealDB configured as its primary, so synced/reconcile logic treats
        it as a real two-store client without a live backend."""
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

    def _write_pending(self, client, kind, record_id, fields):
        client._mirror_write(
            kind, record_id, fields, synced=False, created_at="2026-06-28T22:00:00+00:00"
        )


class TestWriteThroughMirror(MirrorTestBase):
    def test_healthy_write_mirrors_synced_true_and_hits_db(self):
        fake = FakeSurreal(result=[[{"id": "decisions:1"}]])
        client = self._configured_client(fake)

        client.log_decision("t", "r", "o", "po", "b", "sha")

        files = self._mirror_files("decision")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("kind: decision", text)
        self.assertIn("synced: true", text)
        self.assertIn("created_at:", text)
        # The body carries the readable field values.
        self.assertIn('"title": "t"', text)
        self.assertIn('"rationale": "r"', text)
        self.assertIn('"author": "po"', text)
        # The DB received exactly one UPSERT keyed by the minted id (== the filename).
        minted = os.path.basename(files[0])[:-3]
        upserts = [(q, p) for q, p in fake.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        self.assertIn(minted, str(upserts[0][1]["id"]))
        self.assertTrue(str(upserts[0][1]["id"]).startswith("decisions:"))

    def test_outage_write_mirrors_synced_false_and_does_not_raise(self):
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            release_id = client.save_release(version="0.3.0", tag="v0.3.0")

        files = self._mirror_files("release")
        self.assertEqual(len(files), 1)
        text = self._read(files[0])
        self.assertIn("kind: release", text)
        self.assertIn("synced: false", text)
        # The write is durable: it returned an id and persisted to the SQLite fallback.
        self.assertIsNotNone(release_id)
        self.assertEqual(client.backend, "sqlite")

    def test_outage_handoff_is_preserved_without_raising(self):
        broken = FakeSurreal()
        broken.always_fail = True
        client = self._configured_client(broken, connect=lambda: False)

        with redirect_stderr(io.StringIO()):
            handoff_id = client.log_handoff("sre", "po", "release", "/p.md", "open")

        files = self._mirror_files("handoff")
        self.assertEqual(len(files), 1)
        self.assertIn("synced: false", self._read(files[0]))
        self.assertIsNotNone(handoff_id)

    def test_all_eight_kinds_are_mirrored_on_a_healthy_write(self):
        fake = FakeSurreal(result=[[{"id": "x:1"}]])
        client = self._configured_client(fake)

        client.log_decision("t", "r", "o", "a", "b", "s")
        client.save_memory("k", "v", "c")
        client.log_issue("gh-1", "title", "bug", "open", None)
        client.create_milestone("m", "d", "2026-07-01", "active")
        client.save_release("v1.0.0")
        client.save_backtest("strat", 1.0, 0.1, 1.2, "{}", "ds", "sha")
        client.save_session("s1", "agent", "task", [{"role": "user", "content": "hi"}])
        client.log_handoff("a", "b", "plan", "/p", "open")

        for kind in [
            "decision",
            "memory",
            "issue",
            "milestone",
            "release",
            "backtest",
            "session",
            "handoff",
        ]:
            files = self._mirror_files(kind)
            self.assertEqual(len(files), 1, kind)
            self.assertIn("synced: true", self._read(files[0]), kind)

    def test_unwritable_mirror_fails_loudly(self):
        # A file where a directory must be makes the mirror write fail; the DB-down
        # swallow must NOT apply to a mirror-write failure.
        blocker = os.path.join(self.temp_dir.name, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        fake = FakeSurreal(result=[])
        client = DatabaseClient(
            db_path=self.sqlite_db_path, mirror_root=os.path.join(blocker, "mirror")
        )
        client._surreal_class = object()
        client.backend = "surrealdb"
        client.db = fake

        with self.assertRaises(RuntimeError):
            client.log_decision("t", "r", "o", "po", "b", "sha")
        # The mirror failed before the DB attempt, so the DB was never touched.
        self.assertEqual(fake.calls, [])

    def test_sqlite_only_config_marks_synced_true(self):
        # No SurrealDB primary configured: SQLite is authoritative, nothing to sync.
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        client.save_memory("k", "v", "c")
        files = self._mirror_files("memory")
        self.assertEqual(len(files), 1)
        self.assertIn("synced: true", self._read(files[0]))


class TestMirrorFrontmatterInjection(MirrorTestBase):
    def test_newline_in_id_cannot_inject_frontmatter(self):
        # A natural-key id carrying a newline (and crafted extra frontmatter) must
        # not break out of the single id line: the encoded id round-trips exactly
        # and no attacker-controlled key appears in the parsed frontmatter.
        evil_id = "k1\nsynced: true\ninjected: pwned"

        rendered = DatabaseClient._render_mirror(
            evil_id, "memory", "2026-06-28T22:00:00+00:00", False, {"key": evil_id}
        )
        meta, payload = DatabaseClient._parse_mirror(rendered)

        self.assertEqual(meta["id"], evil_id, "the id must round-trip unchanged")
        self.assertNotIn("injected", meta, "a newline must not inject a new key")
        self.assertFalse(meta["synced"], "the real synced flag must stand")
        # The full write path round-trips the same id back from disk.
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        path = client._mirror_write("memory", evil_id, {"key": evil_id}, synced=False)
        with open(path, "r", encoding="utf-8") as handle:
            disk_meta, _ = DatabaseClient._parse_mirror(handle.read())
        self.assertEqual(disk_meta["id"], evil_id)
        self.assertNotIn("injected", disk_meta)


class TestReconcile(MirrorTestBase):
    def test_reconcile_replays_pending_once_idempotent(self):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()
        fake = FakeSurreal(result=[])
        client.backend = "surrealdb"
        client.db = fake
        self._write_pending(client, "release", "release-1", {"version": "0.3.0", "tag": "v0.3.0"})

        result = client.reconcile()

        self.assertEqual(result, {"synced": 1, "remaining": 0})
        upserts = [(q, p) for q, p in fake.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        self.assertIn("release-1", str(upserts[0][1]["id"]))
        files = self._mirror_files("release")
        self.assertEqual(len(files), 1)
        self.assertIn("synced: true", self._read(files[0]))

        # A second run finds nothing pending and issues no further DB calls.
        result2 = client.reconcile()
        self.assertEqual(result2, {"synced": 0, "remaining": 0})
        self.assertEqual(len([1 for q, _ in fake.calls if "UPSERT" in q]), 1)

    def test_reconcile_recovers_connection_then_replays(self):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()
        client.backend = "sqlite"  # currently degraded, no live primary
        client.db = None
        self._write_pending(
            client,
            "decision",
            "decision-1",
            {
                "title": "t",
                "rationale": "r",
                "outcome": "o",
                "author": "a",
                "branch": "b",
                "commit_sha": "s",
            },
        )

        recovered = FakeSurreal(result=[])

        def connect():
            client.db = recovered
            return True

        client._connect_surreal = connect

        result = client.reconcile()

        self.assertEqual(result, {"synced": 1, "remaining": 0})
        self.assertEqual(client.backend, "surrealdb")
        self.assertTrue(any("UPSERT" in q for q, _ in recovered.calls))
        self.assertIn("synced: true", self._read(self._mirror_files("decision")[0]))

    def test_partial_reconcile_leaves_remainder_pending(self):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        client._surreal_class = object()

        calls = {"n": 0}

        def replay_then_drop(query, params=None):
            calls["n"] += 1
            if calls["n"] >= 2:  # the connection drops after the first replay
                raise Exception(TRANSPORT_ERROR)
            return []

        fake = FakeSurreal(result=replay_then_drop)
        client.backend = "surrealdb"
        client.db = fake

        for i in range(3):
            self._write_pending(client, "release", f"release-{i}", {"version": f"v{i}"})

        result = client.reconcile()

        self.assertEqual(result, {"synced": 1, "remaining": 2})
        files = self._mirror_files("release")
        synced = sum("synced: true" in self._read(p) for p in files)
        pending = sum("synced: false" in self._read(p) for p in files)
        self.assertEqual(synced, 1)
        self.assertEqual(pending, 2)

    def test_reconcile_without_primary_reports_all_pending(self):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        # _surreal_class stays None: no SurrealDB primary to reconcile against.
        self._write_pending(
            client, "memory", "k1", {"key": "k1", "value": "v", "category": "c"}
        )
        self.assertEqual(client.reconcile(), {"synced": 0, "remaining": 1})

    def test_reconcile_with_no_pending_is_noop(self):
        client = DatabaseClient(db_path=self.sqlite_db_path, mirror_root=self.mirror_root)
        self.assertEqual(client.reconcile(), {"synced": 0, "remaining": 0})


class TestMemorySyncCLI(unittest.TestCase):
    def test_memory_sync_runs_reconcile_and_reports_counts(self):
        from solomon_harness import cli

        with tempfile.TemporaryDirectory() as tmp:
            mirror_root = os.path.join(tmp, "mirror")
            directory = os.path.join(mirror_root, "release")
            os.makedirs(directory)
            with open(os.path.join(directory, "release-1.md"), "w", encoding="utf-8") as f:
                f.write(
                    "---\nid: release-1\nkind: release\n"
                    "created_at: 2026-06-28T22:00:00+00:00\nsynced: false\n---\n\n"
                    '# release record\n\n```json\n{"version": "0.3.0"}\n```\n'
                )
            out = io.StringIO()
            # No SurrealDB primary in this temp workspace, so reconcile reports the
            # record as still pending; the CLI must run reconcile and print counts.
            with patch.dict(os.environ, {"HARNESS_MIRROR_ROOT": mirror_root}):
                with redirect_stdout(out):
                    cli.main(harness_dir=tmp, argv=["memory", "sync"])
        text = out.getvalue()
        self.assertIn("0 reconciled", text)
        self.assertIn("1 pending", text)


if __name__ == "__main__":
    unittest.main()
