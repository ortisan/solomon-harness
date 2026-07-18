"""Multi-model SurrealDB tests for DatabaseClient.

SurrealDB is used as a true multi-model store: relational (indexes), graph
(RELATE edges and traversals), timeseries (the metrics table and bucketed
aggregation), and vector (HNSW KNN over memory embeddings). These tests cover
both layers of the contract:

- LIVE integration tests, gated on a reachable SurrealDB at ws://localhost:8099.
  Each runs in a THROWAWAY database (``test_mm_<uuid>``) inside the ``solomon``
  namespace and removes it in tearDown, so the real project tenant is never
  touched.
- Backend-agnostic UNIT tests that mock ``_run_surreal`` (or use the real SQLite
  path) to assert the RELATE / KNN / metric queries are constructed correctly, so
  coverage holds in CI where no SurrealDB is running.
"""

import json
import os
import socket
import sys
import tempfile
import unittest
import uuid
from unittest.mock import MagicMock

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    DatabaseClient,
    Embedder,
    EMBEDDING_DIM,
    HashingEmbedder,
)

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

# The DEFINEs the methods under test depend on, run in the throwaway tenant. This
# mirrors the constructor's init block for the tables these tests exercise.
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
    "DEFINE INDEX IF NOT EXISTS sessions_timestamp ON sessions FIELDS timestamp; "
    "DEFINE INDEX IF NOT EXISTS handoffs_timestamp ON handoffs FIELDS timestamp; "
    "DEFINE INDEX IF NOT EXISTS loop_runs_created_at ON loop_runs FIELDS created_at; "
    "DEFINE INDEX IF NOT EXISTS memory_embedding ON memory "
    f"FIELDS embedding HNSW DIMENSION {EMBEDDING_DIM} DIST COSINE TYPE F32;"
)


class _RecordingEmbedder:
    """A deterministic embedder that records every text it is asked to embed."""

    def __init__(self, vector=None):
        self.calls = []
        self._vector = vector if vector is not None else [0.25] * EMBEDDING_DIM

    def embed(self, text):
        self.calls.append(text)
        return list(self._vector)


class TestHashingEmbedder(unittest.TestCase):
    def test_is_an_embedder(self):
        self.assertIsInstance(HashingEmbedder(), Embedder)

    def test_dimension_and_unit_norm(self):
        vec = HashingEmbedder().embed("the quick brown fox")
        self.assertEqual(len(vec), EMBEDDING_DIM)
        norm = sum(v * v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_empty_text_is_zero_vector(self):
        vec = HashingEmbedder().embed("")
        self.assertEqual(len(vec), EMBEDDING_DIM)
        self.assertEqual(sum(abs(v) for v in vec), 0.0)

    def test_shared_tokens_are_nearer_than_unrelated(self):
        emb = HashingEmbedder()

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))

        base = emb.embed("python database query engine")
        overlapping = emb.embed("python database index tuning")
        unrelated = emb.embed("guitar mountain ocean sunset")
        self.assertGreater(cos(base, overlapping), cos(base, unrelated))

    def test_custom_dimension(self):
        vec = HashingEmbedder(dim=16).embed("alpha beta gamma")
        self.assertEqual(len(vec), 16)


class TestEmbedderWiring(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")

    def tearDown(self):
        os.environ.pop("HARNESS_MIRROR_ROOT", None)
        self.temp_dir.cleanup()

    def _client(self, **kwargs):
        return DatabaseClient(
            db_path=os.path.join(self.temp_dir.name, "h.db"), **kwargs
        )

    def test_default_embedder_is_hashing(self):
        self.assertIsInstance(self._client()._embedder, HashingEmbedder)

    def test_injected_embedder_is_used(self):
        fake = _RecordingEmbedder()
        self.assertIs(self._client(embedder=fake)._embedder, fake)

    def test_sqlite_save_memory_does_not_compute_embedding(self):
        # The SQLite fallback has no vector column, so no embedding is computed:
        # save_memory stays cheap and fully backward-compatible there.
        fake = _RecordingEmbedder()
        client = self._client(embedder=fake)
        client.save_memory("k1", "hello world", "notes")
        self.assertEqual(fake.calls, [])
        self.assertEqual(client.get_memory("k1"), "hello world")

    def test_surreal_save_memory_embeds_key_and_value(self):
        # On the SurrealDB branch the embedding is computed from "<key> <value>"
        # and passed as a bound parameter, additively to the existing content.
        fake = _RecordingEmbedder(vector=[0.5] * EMBEDDING_DIM)
        client = self._client(embedder=fake)
        client.backend = "surrealdb"
        client._run_surreal = MagicMock(return_value=[{"id": "memory:k1"}])
        client.save_memory("greet", "hello world", "notes")
        self.assertEqual(fake.calls, ["greet hello world"])
        query, params = client._run_surreal.call_args[0]
        self.assertIn("embedding: $embedding", query)
        self.assertEqual(params["embedding"], [0.5] * EMBEDDING_DIM)
        self.assertEqual(params["value"], "hello world")


class TestMultiModelUnit(unittest.TestCase):
    """Backend-agnostic query-construction and guard tests (no live server)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")

    def tearDown(self):
        os.environ.pop("HARNESS_MIRROR_ROOT", None)
        self.temp_dir.cleanup()

    def _sqlite_client(self):
        return DatabaseClient(db_path=os.path.join(self.temp_dir.name, "h.db"))

    def _surreal_mock_client(self, result=None):
        client = self._sqlite_client()
        client.backend = "surrealdb"
        client._run_surreal = MagicMock(return_value=result if result is not None else [])
        return client

    # --- graph construction ---

    def test_relate_builds_directed_edge_query(self):
        client = self._surreal_mock_client(result=[{"id": "blocks:1"}])
        client.block_issue("1", "2")
        query, params = client._run_surreal.call_args[0]
        self.assertIn("RELATE $rel_from->blocks->$rel_to", query)
        # Every edge is stamped with its minted record_id so a reconcile replay
        # can tell an already-replayed edge from a missing one (ADR-0016).
        self.assertIn("SET record_id = $record_id", query)
        self.assertTrue(str(params["record_id"]).startswith("edge-"))
        # The binary key is bracket-free; str() wraps numeric-looking ids in
        # angle-bracket delimiters, so assert on the RecordID components instead.
        self.assertEqual((params["rel_from"].table_name, params["rel_from"].id), ("issues", "1"))
        self.assertEqual((params["rel_to"].table_name, params["rel_to"].id), ("issues", "2"))

    def test_relate_with_fields_builds_set_clause(self):
        client = self._surreal_mock_client(result=[{"id": "blocks:1"}])
        client.block_issue("1", "2", reason="dependency")
        query, params = client._run_surreal.call_args[0]
        self.assertIn(
            "RELATE $rel_from->blocks->$rel_to SET record_id = $record_id, reason = $reason",
            query,
        )
        self.assertEqual(params["reason"], "dependency")

    def test_relate_rejects_unsafe_edge_name(self):
        client = self._surreal_mock_client()
        with self.assertRaises(ValueError):
            client.relate("blocks; REMOVE DATABASE x", "issues:1", "issues:2")
        client._run_surreal.assert_not_called()

    def test_relate_rejects_unsafe_field_name(self):
        client = self._surreal_mock_client()
        with self.assertRaises(ValueError):
            client.relate("blocks", "issues:1", "issues:2", **{"bad name": 1})
        client._run_surreal.assert_not_called()

    def test_traversal_query_uses_arrow_path(self):
        client = self._surreal_mock_client(result=[{"items": []}])
        client.issues_blocking("5")
        query, params = client._run_surreal.call_args[0]
        self.assertIn("->blocks->issues", query)
        self.assertIn("array::distinct", query)
        self.assertEqual((params["node"].table_name, params["node"].id), ("issues", "5"))

    def test_blocked_by_uses_incoming_arrow(self):
        client = self._surreal_mock_client(result=[{"items": []}])
        client.issues_blocked_by("7")
        query, _ = client._run_surreal.call_args[0]
        self.assertIn("<-blocks<-issues", query)

    def test_as_rid_strips_complex_id_delimiters(self):
        # SurrealDB returns a complex record id wrapped in angle brackets; the
        # rebuilt RecordID's key must match the stored record, not a bracketed key.
        rid = DatabaseClient._as_rid("decisions", "decisions:⟨decision-1Z-ab⟩")
        self.assertEqual((rid.table_name, rid.id), ("decisions", "decision-1Z-ab"))

    # --- graph guards on the SQLite fallback ---

    def test_graph_methods_require_surreal(self):
        client = self._sqlite_client()
        for call in (
            lambda: client.relate("blocks", "issues:1", "issues:2"),
            lambda: client.block_issue("1", "2"),
            lambda: client.issues_blocking("1"),
            lambda: client.milestone_issues("milestones:1"),
            lambda: client.supersedes_chain("decisions:1"),
        ):
            with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
                call()

    # --- vector construction + guards ---

    def test_semantic_search_builds_knn_query(self):
        client = self._surreal_mock_client(result=[])
        client.semantic_search("italian pizza", k=3, category="notes")
        query, params = client._run_surreal.call_args[0]
        self.assertIn("<|3,64|>", query)
        self.assertIn("vector::distance::knn()", query)
        self.assertIn("category = $category", query)
        self.assertIn("ORDER BY distance", query)
        self.assertEqual(params["category"], "notes")
        self.assertEqual(len(params["q"]), EMBEDDING_DIM)

    def test_semantic_search_without_category_omits_filter(self):
        client = self._surreal_mock_client(result=[])
        client.semantic_search("rocket launch", k=5, ef=128)
        query, params = client._run_surreal.call_args[0]
        self.assertIn("<|5,128|>", query)
        self.assertNotIn("category = $category", query)
        self.assertNotIn("category", params)

    def test_semantic_search_requires_surreal(self):
        client = self._sqlite_client()
        with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
            client.semantic_search("anything")

    # --- timeseries construction, guards, and the SQLite path ---

    def test_aggregate_metric_rejects_bad_bucket_and_agg(self):
        client = self._surreal_mock_client()
        with self.assertRaises(ValueError):
            client.aggregate_metric("lat", bucket="fortnight")
        with self.assertRaises(ValueError):
            client.aggregate_metric("lat", agg="median")

    def test_aggregate_metric_builds_time_group_query(self):
        client = self._surreal_mock_client(result=[])
        client.aggregate_metric("lat", bucket="day", agg="mean")
        query, params = client._run_surreal.call_args[0]
        self.assertIn("time::group(time, $bucket)", query)
        self.assertIn("math::mean(value)", query)
        self.assertIn("GROUP BY bucket", query)
        self.assertEqual(params["bucket"], "day")

    def test_metric_aggregations_require_surreal(self):
        client = self._sqlite_client()
        for call in (
            lambda: client.aggregate_metric("lat"),
            lambda: client.loop_run_throughput(),
            lambda: client.loop_run_failure_rate(),
        ):
            with self.assertRaisesRegex(RuntimeError, "requires the SurrealDB backend"):
                call()

    def test_record_and_query_metric_on_sqlite(self):
        client = self._sqlite_client()
        client.record_metric("latency", 1.0, tags={"stage": "dev"}, at="2026-06-01T00:00:00+00:00")
        client.record_metric("latency", 2.0, tags={"stage": "prod"}, at="2026-06-02T00:00:00+00:00")
        rows = client.query_metric("latency")
        self.assertEqual([r["value"] for r in rows], [2.0, 1.0])
        self.assertEqual(rows[0]["tags"], {"stage": "prod"})

    def test_query_metric_since_filter_on_sqlite(self):
        client = self._sqlite_client()
        client.record_metric("latency", 1.0, at="2026-06-01T00:00:00+00:00")
        client.record_metric("latency", 2.0, at="2026-06-02T00:00:00+00:00")
        rows = client.query_metric("latency", since="2026-06-02T00:00:00+00:00")
        self.assertEqual([r["value"] for r in rows], [2.0])

    def test_query_metric_limit_on_sqlite(self):
        client = self._sqlite_client()
        for i in range(5):
            client.record_metric("latency", float(i), at=f"2026-06-0{i + 1}T00:00:00+00:00")
        rows = client.query_metric("latency", limit=2)
        self.assertEqual(len(rows), 2)


class TestTimeOrderedIndexesAreDefined(unittest.TestCase):
    """The time-ordered hot paths carry a supporting index (CI-safe).

    get_latest_activity orders sessions and handoffs by ``timestamp``, and the
    loop-run aggregations filter/group loop_runs by ``created_at``. Without an
    index each is a table scan plus sort on every session start. This asserts the
    production schema declares the index; the live class proves the planner uses
    it.
    """

    _EXPECTED = (
        "DEFINE INDEX IF NOT EXISTS sessions_timestamp ON sessions FIELDS timestamp",
        "DEFINE INDEX IF NOT EXISTS handoffs_timestamp ON handoffs FIELDS timestamp",
        "DEFINE INDEX IF NOT EXISTS loop_runs_created_at ON loop_runs FIELDS created_at",
    )

    def test_schema_statements_declare_time_indexes(self):
        joined = " ".join(DatabaseClient._SURREAL_SCHEMA_STATEMENTS)
        for expected in self._EXPECTED:
            self.assertIn(expected, joined)


@unittest.skipUnless(SURREAL_AVAILABLE, "SurrealDB not reachable at " + SURREAL_URL)
class TestMultiModelLive(unittest.TestCase):
    """Live round-trips against a throwaway SurrealDB tenant."""

    def setUp(self):
        import surrealdb

        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(self.temp_dir.name, "mirror")
        self.client = DatabaseClient(db_path=os.path.join(self.temp_dir.name, "h.db"))
        self.dbname = f"test_mm_{uuid.uuid4().hex}"
        self.raw = surrealdb.Surreal(SURREAL_URL)
        if hasattr(self.raw, "connect"):
            self.raw.connect()
        self.raw.signin({"username": "root", "password": "root"})
        self.raw.use("solomon", self.dbname)
        self.raw.query(_INIT_DEFINES)
        self.client.backend = "surrealdb"
        self.client.db = self.raw

    def tearDown(self):
        try:
            self.raw.query(f"REMOVE DATABASE {self.dbname};")
        finally:
            try:
                self.raw.close()
            except Exception:
                pass
            os.environ.pop("HARNESS_MIRROR_ROOT", None)
            self.temp_dir.cleanup()

    # --- get-by-id round-trips (regression: complex-id delimiter strip) ---

    def test_get_decision_round_trip_on_surreal(self):
        # SurrealDB v3.x renders a minted complex key wrapped in angle brackets;
        # _parse_rid must strip them so a get-by-id matches the stored record
        # instead of returning None.
        decision_id = self.client.log_decision(
            "title", "rationale", "outcome", "author", "main", "sha1234"
        )
        fetched = self.client.get_decision(decision_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "title")

    def test_get_milestone_round_trip_on_surreal(self):
        milestone_id = self.client.create_milestone("M1", "desc", "2026-07-01", "active")
        fetched = self.client.get_milestone(milestone_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "M1")

    # --- relational ---

    def test_relational_indexes_are_defined(self):
        info = self.raw.query("INFO FOR TABLE issues")
        indexes = info["indexes"]
        self.assertIn("issues_github_id", indexes)
        self.assertIn("issues_status", indexes)
        self.assertIn("UNIQUE", indexes["issues_github_id"])

    def test_time_ordered_indexes_are_defined(self):
        # The production bootstrap (not the test's partial _INIT_DEFINES mirror)
        # is what must create these, so drive it directly against the tenant.
        self.client._bootstrap_surreal_schema()
        for table, index in (
            ("sessions", "sessions_timestamp"),
            ("handoffs", "handoffs_timestamp"),
            ("loop_runs", "loop_runs_created_at"),
        ):
            info = self.raw.query(f"INFO FOR TABLE {table}")
            self.assertIn(index, info["indexes"], f"{index} missing on {table}")

    def test_latest_activity_query_uses_the_timestamp_index(self):
        # get_latest_activity orders sessions by timestamp DESC LIMIT 1. With the
        # index the planner must switch from TableScan + sort to an IndexScan, the
        # same plan decisions already gets on its created_at index.
        self.client._bootstrap_surreal_schema()
        for i in range(3):
            self.client.save_session(f"s{i}", "agent", "task", [])
        plan = json.dumps(
            self.raw.query("SELECT * FROM sessions ORDER BY timestamp DESC LIMIT 1 EXPLAIN"),
            default=str,
        )
        self.assertIn("IndexScan", plan)
        self.assertIn("sessions_timestamp", plan)
        self.assertNotIn("TableScan", plan)

    def test_loop_run_since_filter_uses_the_created_at_index(self):
        # loop_run_throughput only gains from the index on the since-filtered path
        # (an unfiltered aggregation must visit every row); this proves the
        # throughput query's range read resolves to an IndexScan on the new index.
        self.client._bootstrap_surreal_schema()
        plan = json.dumps(
            self.raw.query(
                "SELECT time::group(created_at, 'day') AS bucket, count() "
                "FROM loop_runs WHERE created_at >= d'2000-01-01T00:00:00Z' "
                "GROUP BY bucket EXPLAIN"
            ),
            default=str,
        )
        self.assertIn("IndexScan", plan)
        self.assertIn("loop_runs_created_at", plan)

    def test_unique_github_id_index_is_enforced(self):
        import surrealdb

        self.raw.query("CREATE issues:dup_a SET github_id = '500';")
        with self.assertRaises(surrealdb.errors.SurrealError):
            self.raw.query("CREATE issues:dup_b SET github_id = '500';")

    # --- graph ---

    def test_block_issue_round_trip_and_traversal(self):
        self.client.log_issue("1", "first", "feature", "open", None)
        self.client.log_issue("2", "second", "feature", "open", None)
        edge_id = self.client.block_issue("1", "2", reason="dependency")
        self.assertIsNotNone(edge_id)

        blocking = self.client.issues_blocking("1")
        self.assertEqual([r["github_id"] for r in blocking], ["2"])
        blocked_by = self.client.issues_blocked_by("2")
        self.assertEqual([r["github_id"] for r in blocked_by], ["1"])
        # An issue with no edges traverses to an empty list, not an error.
        self.assertEqual(self.client.issues_blocking("2"), [])

    def test_log_issue_persists_and_reads_back_assignee(self):
        """The canonical person key round-trips through the live SurrealDB issue
        UPSERT, and a 5-arg write (no assignee) reads back with no key set."""
        self.client.log_issue(
            "a1", "Assigned", "feature", "open", None, assignee="alice@example.com"
        )
        self.client.log_issue("a2", "Unassigned", "feature", "open", None)
        assigned = self.client.get_issue("a1")
        unassigned = self.client.get_issue("a2")
        self.assertEqual(assigned["assignee"], "alice@example.com")
        self.assertIsNone(unassigned.get("assignee"))

    def test_supersedes_chain_is_transitive(self):
        d1 = self.client.log_decision("oldest", "r", "o", "a", "main", "s1")
        d2 = self.client.log_decision("middle", "r", "o", "a", "main", "s2")
        d3 = self.client.log_decision("newest", "r", "o", "a", "main", "s3")
        self.client.supersede_decision(d3, d2)
        self.client.supersede_decision(d2, d1)
        chain = self.client.supersedes_chain(d3)
        self.assertEqual([r["title"] for r in chain], ["middle", "oldest"])

    def test_milestone_contains_issue(self):
        mid = self.client.create_milestone("m1", "desc", "2026-07-01", "active")
        self.client.log_issue("10", "child", "feature", "open", None)
        self.client.assign_issue_to_milestone(mid, "10")
        issues = self.client.milestone_issues(mid)
        self.assertEqual([r["github_id"] for r in issues], ["10"])

    def test_session_produced_handoff_and_decision_addresses_issue(self):
        self.client.save_session("sess-1", "agent", "task", [{"role": "user", "content": "hi"}])
        handoff_id = self.client.log_handoff("a", "b", "ctype", "/path", "open")
        self.assertIsNotNone(self.client.link_session_handoff("sess-1", handoff_id))

        d1 = self.client.log_decision("d1", "r", "o", "a", "main", "s1")
        self.client.log_issue("20", "issue", "bug", "open", None)
        self.assertIsNotNone(self.client.decision_addresses_issue(d1, "20"))

        produced = self.raw.query("SELECT in, out FROM produced")
        self.assertEqual(len(produced), 1)
        self.assertEqual(
            (produced[0]["in"].table_name, produced[0]["in"].id), ("sessions", "sess-1")
        )
        addresses = self.raw.query("SELECT out FROM addresses")
        self.assertEqual(
            (addresses[0]["out"].table_name, addresses[0]["out"].id), ("issues", "20")
        )

    # --- timeseries ---

    def test_record_query_and_aggregate_metric(self):
        self.client.record_metric("latency", 10.0, tags={"stage": "dev"})
        self.client.record_metric("latency", 30.0, tags={"stage": "dev"})
        rows = self.client.query_metric("latency")
        self.assertEqual(sorted(r["value"] for r in rows), [10.0, 30.0])

        mean = self.client.aggregate_metric("latency", bucket="day", agg="mean")
        self.assertEqual(len(mean), 1)
        self.assertAlmostEqual(mean[0]["value"], 20.0)
        count = self.client.aggregate_metric("latency", bucket="day", agg="count")
        self.assertEqual(count[0]["value"], 2)

    def test_loop_run_throughput_and_failure_rate(self):
        self.client.save_loop_run("dev", "t", "go", "success", "sess-1")
        self.client.save_loop_run("dev", "t", "go", "failure", "sess-1")
        self.client.save_loop_run("review", "t", "go", "success", "sess-1")

        throughput = self.client.loop_run_throughput(bucket="day")
        self.assertEqual(sum(r["count"] for r in throughput), 3)

        rate = self.client.loop_run_failure_rate()
        self.assertEqual(rate["total"], 3)
        self.assertEqual(rate["failures"], 1)
        self.assertAlmostEqual(rate["failure_rate"], 1 / 3)

    # --- vector ---

    def test_semantic_search_returns_lexically_nearest(self):
        self.client.save_memory("greet", "hello world greeting message", "notes")
        self.client.save_memory("food", "pizza pasta italian cuisine", "notes")
        self.client.save_memory("space", "rocket astronaut orbit launch", "notes")

        hits = self.client.semantic_search("italian pizza dinner", k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["key"], "food")
        # Distance is non-decreasing (nearest first).
        distances = [h["distance"] for h in hits]
        self.assertEqual(distances, sorted(distances))

    def test_semantic_search_respects_category_filter(self):
        self.client.save_memory("a", "shared term apple", "fruit")
        self.client.save_memory("b", "shared term banana", "fruit")
        self.client.save_memory("c", "shared term carbon", "chem")
        hits = self.client.semantic_search("shared term", k=5, category="fruit")
        self.assertTrue(hits)
        self.assertTrue(all(h["category"] == "fruit" for h in hits))


if __name__ == "__main__":
    unittest.main()
