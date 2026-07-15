import os
import socket
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from solomon_harness.memory_service import MemoryService, resolve_harness_dir  # noqa: E402

SURREAL_URL = os.environ.get("SURREAL_URL", "ws://localhost:8099/rpc")


def _host_port(url):
    """Best-effort (host, port) parse of a ws:// URL for a cheap TCP probe."""
    rest = url.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        return host, int(port)
    return hostport, 8000


def _surreal_reachable():
    """True only if a SurrealDB server answers a sign-in on the configured URL."""
    host, port = _host_port(SURREAL_URL)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        return False
    try:
        import surrealdb

        db = surrealdb.Surreal(SURREAL_URL)
        if hasattr(db, "connect"):
            db.connect()
        db.signin({"username": "root", "password": "root"})
        db.use("solomon", "test_mm_probe")
        db.close()
        return True
    except Exception:
        return False


SURREAL_AVAILABLE = _surreal_reachable()

# The DEFINEs the multimodel wrappers depend on, run in a throwaway tenant; this
# mirrors tests/test_database_client_multimodel.py so the service-level live tests
# never touch the real project tenant.
from solomon_harness.tools.database_client import EMBEDDING_DIM  # noqa: E402

_INIT_DEFINES = (
    "DEFINE TABLE IF NOT EXISTS decisions SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS memory SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS milestones SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS issues SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS sessions SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS handoffs SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS loop_runs SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS metrics SCHEMALESS; "
    "DEFINE TABLE IF NOT EXISTS blocks TYPE RELATION; "
    "DEFINE TABLE IF NOT EXISTS supersedes TYPE RELATION; "
    "DEFINE TABLE IF NOT EXISTS contains TYPE RELATION; "
    "DEFINE TABLE IF NOT EXISTS produced TYPE RELATION; "
    "DEFINE TABLE IF NOT EXISTS addresses TYPE RELATION; "
    "DEFINE INDEX IF NOT EXISTS issues_github_id ON issues FIELDS github_id UNIQUE; "
    "DEFINE INDEX IF NOT EXISTS issues_status ON issues FIELDS status; "
    "DEFINE INDEX IF NOT EXISTS decisions_created_at ON decisions FIELDS created_at; "
    "DEFINE INDEX IF NOT EXISTS metrics_name_time ON metrics FIELDS name, time; "
    "DEFINE INDEX IF NOT EXISTS memory_embedding ON memory "
    f"FIELDS embedding HNSW DIMENSION {EMBEDDING_DIM} DIST COSINE TYPE F32;"
)


class TestMemoryService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from unittest.mock import patch
        self.patcher = patch("os.path.isfile", side_effect=lambda path: False if "config.json" in path else os.path.isfile(path))
        self.patcher.start()
        self.svc = MemoryService(db_path=os.path.join(self.tmp.name, "memory.db"))

    def tearDown(self):
        self.svc.close()
        self.patcher.stop()
        self.tmp.cleanup()

    def test_decision_roundtrip(self):
        result = self.svc.save_decision("Adopt MCP", "expose memory", "Approved", "qa")
        decision_id = result["decision_id"]
        self.assertIsNotNone(decision_id)
        decision = self.svc.get_decision(decision_id)["decision"]
        self.assertEqual(decision["title"], "Adopt MCP")

    def test_memory_roundtrip(self):
        self.svc.save_memory("k", "v", "cat")
        self.assertEqual(self.svc.get_memory("k")["value"], "v")

    def test_get_backend_status_reports_sqlite(self):
        # An explicit db_path is a deliberate SQLite choice, so the service
        # reports the backend without flagging degradation (issue #163).
        self.assertEqual(
            self.svc.get_backend_status(),
            {"backend": "sqlite", "degraded": False, "fallback_reason": None},
        )

    def test_open_issues(self):
        self.svc.log_issue("gh-1", "Open one", "feature", "open")
        self.svc.log_issue("gh-2", "Closed one", "bug", "closed")
        issues = self.svc.get_open_issues()["issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["github_id"], "gh-1")
        self.assertEqual(self.svc.get_issue("gh-1")["issue"]["title"], "Open one")

    def test_session_handoff_and_latest_activity(self):
        self.svc.save_session("s1", "qa", "ship it", [{"role": "user", "content": "hi"}])
        session = self.svc.get_session("s1")["session"]
        self.assertEqual(session["agent_name"], "qa")

        handoff = self.svc.log_handoff("qa", "sre", "plan", "/p", "pending")
        self.assertIsNotNone(handoff["handoff_id"])

        activity = self.svc.get_latest_activity()["activity"]
        self.assertIsNotNone(activity)

    def test_handoff_lifecycle_summary_and_status_update(self):
        handoff = self.svc.log_handoff(
            "qa", "sre", "release", "/r.md", "ready", summary="suite green, ready to cut"
        )
        hid = handoff["handoff_id"]
        self.assertIsNotNone(hid)

        # The write seam normalized ready -> open (ADR-0016).
        activity = self.svc.get_latest_activity()["activity"]
        self.assertEqual(activity["status"], "open")
        self.assertEqual(activity["summary"], "suite green, ready to cut")

        updated = self.svc.update_handoff_status(hid, "accepted")
        self.assertTrue(updated["ok"])
        self.assertEqual(self.svc.get_latest_activity()["activity"]["status"], "accepted")

    def test_update_handoff_status_missing_row_reports_not_ok(self):
        self.assertFalse(self.svc.update_handoff_status(424242, "done")["ok"])

    def test_save_session_persists_status(self):
        self.svc.save_session("s9", "qa", "wrap up", [], status="done")
        self.assertEqual(self.svc.get_session("s9")["session"]["status"], "done")

    def test_save_session_links_worked_on_issues(self):
        # The issues parameter reaches the client and produces worked_on links
        # (ADR-0018); a missing issue row is created rather than dangled.
        self.svc.save_session("s10", "qa", "review the fix", [], issues=[321])
        issue = self.svc.get_issue("321")["issue"]
        self.assertIsNotNone(issue)
        with self.svc.client._sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT source_id, github_id FROM worked_on")
            rows = [dict(r) for r in cur.fetchall()]
        self.assertEqual(rows, [{"source_id": "s10", "github_id": "321"}])

    def test_milestones_and_releases(self):
        mid = self.svc.create_milestone("M1", "goals", "2026-07-01", "active")["milestone_id"]
        self.assertEqual(len(self.svc.list_milestones()["milestones"]), 1)

        rid = self.svc.save_release(
            "v1.0.0", tag="v1.0.0", notes="first", issue_github_id="42", milestone_id=str(mid)
        )["release_id"]
        self.assertIsNotNone(rid)
        rel = self.svc.get_release(rid)["release"]
        self.assertEqual(rel["version"], "v1.0.0")
        self.assertEqual(rel["issue_github_id"], "42")
        self.assertEqual(len(self.svc.list_releases()["releases"]), 1)

    def test_resolve_harness_dir_finds_package(self):
        self.assertEqual(resolve_harness_dir(WORKSPACE), WORKSPACE)

    # --- timeseries on the SQLite fallback ---

    def test_record_and_query_metric_roundtrip(self):
        first = self.svc.record_metric(
            "latency", 1.5, tags={"stage": "dev"}, at="2026-06-01T00:00:00+00:00"
        )
        self.assertIn("metric_id", first)
        self.svc.record_metric("latency", 2.5, at="2026-06-02T00:00:00+00:00")
        results = self.svc.query_metric("latency")["results"]
        self.assertEqual([row["value"] for row in results], [2.5, 1.5])
        self.assertEqual(results[1]["tags"], {"stage": "dev"})

    def test_query_metric_since_filter(self):
        self.svc.record_metric("latency", 1.0, at="2026-06-01T00:00:00+00:00")
        self.svc.record_metric("latency", 2.0, at="2026-06-02T00:00:00+00:00")
        results = self.svc.query_metric(
            "latency", since="2026-06-02T00:00:00+00:00"
        )["results"]
        self.assertEqual([row["value"] for row in results], [2.0])

    # --- SurrealDB-only wrappers surface the guard on SQLite ---

    def test_graph_wrappers_require_surreal(self):
        for call in (
            lambda: self.svc.relate("blocks", "issues:1", "issues:2"),
            lambda: self.svc.block_issue("1", "2"),
            lambda: self.svc.supersede_decision("decisions:2", "decisions:1"),
            lambda: self.svc.assign_issue_to_milestone("milestones:1", "1"),
            lambda: self.svc.link_session_handoff("sessions:1", "handoffs:1"),
            lambda: self.svc.decision_addresses_issue("decisions:1", "1"),
            lambda: self.svc.issues_blocking("1"),
            lambda: self.svc.issues_blocked_by("1"),
            lambda: self.svc.milestone_issues("milestones:1"),
            lambda: self.svc.supersedes_chain("decisions:1"),
        ):
            with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
                call()

    def test_metric_aggregation_wrappers_require_surreal(self):
        for call in (
            lambda: self.svc.aggregate_metric("latency"),
            lambda: self.svc.loop_run_throughput(),
            lambda: self.svc.loop_run_failure_rate(),
        ):
            with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
                call()

    def test_semantic_search_requires_surreal(self):
        with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
            self.svc.semantic_search("anything")


@unittest.skipUnless(SURREAL_AVAILABLE, "SurrealDB not reachable at " + SURREAL_URL)
class TestMemoryServiceMultiModelLive(unittest.TestCase):
    """Live round-trips of the multimodel wrappers against a throwaway tenant."""

    def setUp(self):
        import surrealdb

        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.tmp.name, "mirror")
        self.patcher = patch(
            "os.path.isfile",
            side_effect=lambda path: False
            if "config.json" in path
            else os.path.isfile(path),
        )
        self.patcher.start()
        self.svc = MemoryService(db_path=os.path.join(self.tmp.name, "memory.db"))
        self.dbname = f"test_mm_{uuid.uuid4().hex}"
        self.raw = surrealdb.Surreal(SURREAL_URL)
        if hasattr(self.raw, "connect"):
            self.raw.connect()
        self.raw.signin({"username": "root", "password": "root"})
        self.raw.use("solomon", self.dbname)
        self.raw.query(_INIT_DEFINES)
        self.svc.client.backend = "surrealdb"
        self.svc.client.db = self.raw

    def tearDown(self):
        try:
            self.raw.close()
        except Exception:
            pass
        finally:
            self.patcher.stop()
            os.environ.pop("HARNESS_MIRROR_ROOT", None)
            self.tmp.cleanup()

    def test_block_issue_round_trip_and_traversal(self):
        self.svc.log_issue("1", "first", "feature", "open")
        self.svc.log_issue("2", "second", "feature", "open")
        edge = self.svc.block_issue("1", "2", reason="dependency")
        self.assertIsNotNone(edge["edge_id"])

        blocking = self.svc.issues_blocking("1")["issues"]
        self.assertEqual([r["github_id"] for r in blocking], ["2"])
        blocked_by = self.svc.issues_blocked_by("2")["issues"]
        self.assertEqual([r["github_id"] for r in blocked_by], ["1"])

    def test_milestone_contains_issue(self):
        mid = self.svc.create_milestone("m1", "desc", "2026-07-01", "active")[
            "milestone_id"
        ]
        self.svc.log_issue("10", "child", "feature", "open")
        self.svc.assign_issue_to_milestone(mid, "10")
        issues = self.svc.milestone_issues(mid)["issues"]
        self.assertEqual([r["github_id"] for r in issues], ["10"])

    def test_supersedes_chain(self):
        d1 = self.svc.save_decision("oldest", "r", "o", "a")["decision_id"]
        d2 = self.svc.save_decision("newer", "r", "o", "a")["decision_id"]
        self.svc.supersede_decision(d2, d1)
        chain = self.svc.supersedes_chain(d2)["decisions"]
        self.assertEqual([r["title"] for r in chain], ["oldest"])

    def test_record_query_and_aggregate_metric(self):
        self.svc.record_metric("latency", 10.0, tags={"stage": "dev"})
        self.svc.record_metric("latency", 30.0, tags={"stage": "dev"})
        rows = self.svc.query_metric("latency")["results"]
        self.assertEqual(sorted(r["value"] for r in rows), [10.0, 30.0])

        buckets = self.svc.aggregate_metric("latency", bucket="day", agg="mean")[
            "buckets"
        ]
        self.assertEqual(len(buckets), 1)
        self.assertAlmostEqual(buckets[0]["value"], 20.0)

    def test_loop_run_throughput_and_failure_rate(self):
        self.svc.client.save_loop_run("dev", "t", "go", "success", "sess-1")
        self.svc.client.save_loop_run("dev", "t", "go", "failure", "sess-1")
        self.svc.client.save_loop_run("review", "t", "go", "success", "sess-1")

        throughput = self.svc.loop_run_throughput(bucket="day")["throughput"]
        self.assertEqual(sum(r["count"] for r in throughput), 3)

        rate = self.svc.loop_run_failure_rate()["failure_rate"]
        self.assertEqual(rate["total"], 3)
        self.assertEqual(rate["failures"], 1)
        self.assertAlmostEqual(rate["failure_rate"], 1 / 3)

    def test_semantic_search_returns_lexically_nearest(self):
        self.svc.save_memory("greet", "hello world greeting message", "notes")
        self.svc.save_memory("food", "pizza pasta italian cuisine", "notes")
        self.svc.save_memory("space", "rocket astronaut orbit launch", "notes")

        hits = self.svc.semantic_search("italian pizza dinner", k=3)["results"]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["key"], "food")


if __name__ == "__main__":
    unittest.main()
