"""Harness invariants that lock in the structural guarantees.

These guard against regressions in the build pipeline and the memory/MCP layer:
- `compile` must never mutate tracked source (the defect Phase 0 fixed).
- The MCP server must actually build with the `mcp` dependency installed.
- The SurrealDB-primary path can be exercised against a live server when one is
  provided, so green CI can reflect a working backend rather than only mocks.
"""

import hashlib
import json
import os
import socket
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _call_tool_json(server, name, arguments):
    """Call an MCP tool and parse its single TextContent reply as JSON.

    ``FastMCP.call_tool`` returns a list of content blocks; every tool here
    replies with one ``TextContent`` carrying a JSON-serialized dict (the
    MemoryService contract), so this is the one place that unwraps it.
    """
    import asyncio

    result = asyncio.run(server.call_tool(name, arguments))
    return json.loads(result[0].text)


def _surreal_reachable(url):
    """Best-effort probe: True only if a SurrealDB server signs in at ``url``.

    Mirrors the live-gate convention in test_database_client_multimodel.py so
    the graph/vector MCP tool tests run for real wherever a SurrealDB is
    reachable, and skip cleanly (never fail) where one is not.
    """
    rest = url.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    host, _, port = hostport.partition(":")
    port_num = int(port) if port else 8000
    try:
        with socket.create_connection((host, port_num), timeout=1.0):
            pass
    except OSError:
        return False
    try:
        import surrealdb

        probe = surrealdb.Surreal(url)
        if hasattr(probe, "connect"):
            probe.connect()
        probe.signin({"username": "root", "password": "root"})
        probe.close()
        return True
    except Exception:
        return False


SURREAL_LIVE_URL = os.environ.get("SURREAL_URL", "ws://localhost:8099/rpc")
SURREAL_LIVE_AVAILABLE = _surreal_reachable(SURREAL_LIVE_URL)


def _hash_tree(root: str) -> dict:
    """Map every file under root to its sha256, skipping caches."""
    digests = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    digests[path] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                pass
    return digests


class TestScaffoldDoesNotMutateSource(unittest.TestCase):
    """Scaffolding must treat agents/ as source and only add missing files."""

    def test_scaffold_leaves_existing_source_unchanged(self):
        from solomon_harness.bootstrap import scaffold_agents

        agents_dir = os.path.join(WORKSPACE, "agents")
        before = _hash_tree(agents_dir)

        scaffold_agents(WORKSPACE)

        after = _hash_tree(agents_dir)

        changed = sorted(p for p in before if p in after and before[p] != after[p])
        created = sorted(p for p in after if p not in before)
        removed = sorted(p for p in before if p not in after)

        # The core invariant: scaffolding must never modify or delete a tracked
        # source file (persona.md, the role profile, .agent/config.json, any skill).
        self.assertEqual(changed, [], f"scaffold mutated existing source files: {changed}")
        self.assertEqual(removed, [], f"scaffold removed files under agents/: {removed}")

        # It may create genuinely-missing entrypoint/config files; nothing else.
        allowed = {"main.py", "config.json"}
        unexpected = [p for p in created if os.path.basename(p) not in allowed]
        self.assertEqual(unexpected, [], f"scaffold created unexpected files: {unexpected}")


class TestMcpServerBuilds(unittest.TestCase):
    """The MCP server must construct with the declared mcp dependency."""

    # The full registered tool set (solomon_harness/mcp_server.py). Kept exact
    # (asserted with assertEqual, not just "at least these") so both a removed
    # tool and an added-but-forgotten one are caught, rather than only the
    # former: the graph/timeseries/vector tools (#134-era additions) once grew
    # past this set unnoticed because the old assertion only checked for
    # missing names, never extras.
    EXPECTED_TOOLS = {
        "save_decision", "get_decision", "save_memory", "get_memory",
        "log_issue", "get_open_issues", "get_issue", "create_milestone",
        "list_milestones", "save_release", "get_release", "list_releases",
        "save_backtest", "save_session", "get_session", "log_handoff",
        "get_latest_activity",
        # Graph (SurrealDB-only).
        "relate", "block_issue", "supersede_decision",
        "assign_issue_to_milestone", "link_session_handoff",
        "decision_addresses_issue", "issues_blocking", "issues_blocked_by",
        "milestone_issues", "supersedes_chain",
        # Timeseries (works on both backends).
        "record_metric", "query_metric", "aggregate_metric",
        "loop_run_throughput", "loop_run_failure_rate",
        # Vector (SurrealDB-only).
        "semantic_search",
    }

    def test_build_server_registers_expected_tools(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp package not installed")

        import asyncio
        import tempfile

        from solomon_harness.mcp_server import build_server

        with tempfile.TemporaryDirectory() as tmp:
            # Point the memory store at a throwaway dir so the test never writes
            # to the real project memory.
            prior = os.environ.get("SOLOMON_HARNESS_DIR")
            os.environ["SOLOMON_HARNESS_DIR"] = tmp
            try:
                server = build_server()
                self.assertIsNotNone(server)
                tools = asyncio.run(server.list_tools())
                names = {t.name for t in tools}
                self.assertEqual(
                    names,
                    self.EXPECTED_TOOLS,
                    f"missing: {self.EXPECTED_TOOLS - names}; "
                    f"unexpected: {names - self.EXPECTED_TOOLS}",
                )
            finally:
                if prior is None:
                    os.environ.pop("SOLOMON_HARNESS_DIR", None)
                else:
                    os.environ["SOLOMON_HARNESS_DIR"] = prior

    def test_call_tool_timeseries_round_trips_on_a_real_database_client(self):
        """call_tool exercises a timeseries tool (record_metric/query_metric)
        against a real DatabaseClient. Timeseries works on both backends, so
        this runs unconditionally (no SurrealDB required) against the SQLite
        fallback in a throwaway harness directory."""
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp package not installed")

        import tempfile

        from solomon_harness.mcp_server import build_server

        with tempfile.TemporaryDirectory() as tmp:
            prior = os.environ.get("SOLOMON_HARNESS_DIR")
            os.environ["SOLOMON_HARNESS_DIR"] = tmp
            try:
                server = build_server()
                recorded = _call_tool_json(
                    server,
                    "record_metric",
                    {"name": "cockpit_latency_ms", "value": 42.5, "tags": {"stage": "test"}},
                )
                self.assertIsNotNone(recorded.get("metric_id"))

                queried = _call_tool_json(
                    server, "query_metric", {"name": "cockpit_latency_ms"}
                )
                values = [row["value"] for row in queried["results"]]
                self.assertEqual(values, [42.5])
            finally:
                if prior is None:
                    os.environ.pop("SOLOMON_HARNESS_DIR", None)
                else:
                    os.environ["SOLOMON_HARNESS_DIR"] = prior


@unittest.skipUnless(
    SURREAL_LIVE_AVAILABLE,
    "no reachable SurrealDB at SURREAL_URL for the live MCP graph/vector tool tests",
)
class TestMcpServerGraphAndVectorTools(unittest.TestCase):
    """call_tool coverage for the SurrealDB-only tool families.

    ``relate``/``block_issue`` (graph) and ``semantic_search`` (vector) raise
    on the SQLite fallback by design, so exercising them for real needs a live
    SurrealDB; this runs against one when reachable (see SURREAL_LIVE_AVAILABLE)
    in a disposable per-test tenant that is removed in tearDown, so it never
    touches the real project's tenant.
    """

    def setUp(self):
        import tempfile

        from solomon_harness.mcp_server import build_server

        self.temp_dir = tempfile.TemporaryDirectory()
        config_dir = os.path.join(self.temp_dir.name, ".agent")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "config.json"), "w", encoding="utf-8") as f:
            f.write('{"database": {"provider": "surrealdb"}}')

        self._prior_url = os.environ.get("SURREAL_URL")
        os.environ["SURREAL_URL"] = SURREAL_LIVE_URL
        self._prior_dir = os.environ.get("SOLOMON_HARNESS_DIR")
        os.environ["SOLOMON_HARNESS_DIR"] = self.temp_dir.name

        self.server = build_server()

    def tearDown(self):
        from solomon_harness.home import derive_tenant

        tenant = derive_tenant(self.temp_dir.name)
        try:
            import surrealdb

            raw = surrealdb.Surreal(SURREAL_LIVE_URL)
            if hasattr(raw, "connect"):
                raw.connect()
            raw.signin({"username": "root", "password": "root"})
            # REMOVE DATABASE requires a bound namespace on the connection.
            raw.use("solomon", tenant)
            raw.query(f"REMOVE DATABASE `{tenant}`;")
            raw.close()
        except Exception:
            pass

        if self._prior_url is None:
            os.environ.pop("SURREAL_URL", None)
        else:
            os.environ["SURREAL_URL"] = self._prior_url
        if self._prior_dir is None:
            os.environ.pop("SOLOMON_HARNESS_DIR", None)
        else:
            os.environ["SOLOMON_HARNESS_DIR"] = self._prior_dir
        self.temp_dir.cleanup()

    def test_call_tool_graph_relate_and_traversal(self):
        """block_issue (a relate wrapper) and issues_blocking round-trip through
        call_tool against a real, live-SurrealDB-backed DatabaseClient."""
        self._call_tool_json(
            "log_issue",
            {"github_id": "gt-1", "title": "blocker", "type_": "bug", "status": "open"},
        )
        self._call_tool_json(
            "log_issue",
            {"github_id": "gt-2", "title": "blocked", "type_": "bug", "status": "open"},
        )
        blocked = self._call_tool_json(
            "block_issue", {"blocker_github_id": "gt-1", "blocked_github_id": "gt-2"}
        )
        self.assertIsNotNone(blocked.get("edge_id"))

        blocking = self._call_tool_json("issues_blocking", {"github_id": "gt-1"})
        self.assertEqual([r["github_id"] for r in blocking["issues"]], ["gt-2"])

    def test_call_tool_vector_semantic_search(self):
        """semantic_search round-trips through call_tool against a real,
        live-SurrealDB-backed DatabaseClient, returning the lexically nearest
        memory entry first."""
        self._call_tool_json(
            "save_memory",
            {"key": "note-1", "value": "italian pizza dinner recipe", "category": "notes"},
        )
        self._call_tool_json(
            "save_memory",
            {"key": "note-2", "value": "rocket launch telemetry data", "category": "notes"},
        )

        found = self._call_tool_json(
            "semantic_search", {"query": "pizza dinner", "k": 1}
        )
        self.assertEqual(len(found["results"]), 1)
        self.assertEqual(found["results"][0]["key"], "note-1")

    def _call_tool_json(self, name, arguments):
        return _call_tool_json(self.server, name, arguments)


@unittest.skipUnless(
    os.environ.get("SURREAL_TEST_URL"),
    "set SURREAL_TEST_URL (and SURREAL_USER/SURREAL_PASS) to run the live SurrealDB test",
)
class TestSurrealIntegration(unittest.TestCase):
    """Exercises the SurrealDB-primary path against a live server when provided."""

    def test_memory_roundtrip_on_surrealdb(self):
        import tempfile

        from solomon_harness.tools.database_client import DatabaseClient

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["SURREAL_URL"] = os.environ["SURREAL_TEST_URL"]
            config_dir = os.path.join(tmp, ".agent")
            os.makedirs(config_dir)
            with open(os.path.join(config_dir, "config.json"), "w", encoding="utf-8") as f:
                f.write('{"database": {"provider": "surrealdb"}}')

            db = DatabaseClient(harness_dir=tmp)
            self.assertEqual(db.backend, "surrealdb", "did not connect to the live SurrealDB")
            db.save_memory("invariant_key", "invariant_value", "test")
            self.assertEqual(db.get_memory("invariant_key"), "invariant_value")
            db.close()


if __name__ == "__main__":
    unittest.main()
