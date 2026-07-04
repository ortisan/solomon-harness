"""Harness invariants that lock in the structural guarantees.

These guard against regressions in the build pipeline and the memory/MCP layer:
- `compile` must never mutate tracked source (the defect Phase 0 fixed).
- The MCP server must actually build with the `mcp` dependency installed.
- The SurrealDB-primary path can be exercised against a live server when one is
  provided, so green CI can reflect a working backend rather than only mocks.
"""

import hashlib
import os
import unittest
from unittest.mock import patch

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    EXPECTED_TOOLS = {
        "save_decision", "get_decision", "save_memory", "get_memory",
        "log_issue", "get_open_issues", "get_issue", "create_milestone",
        "save_backtest", "save_session", "get_session", "log_handoff",
        "get_latest_activity",
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
                missing = self.EXPECTED_TOOLS - names
                self.assertEqual(missing, set(), f"MCP server missing tools: {missing}")
            finally:
                if prior is None:
                    os.environ.pop("SOLOMON_HARNESS_DIR", None)
                else:
                    os.environ["SOLOMON_HARNESS_DIR"] = prior


@unittest.skipUnless(
    os.environ.get("SURREAL_TEST_URL"),
    "set SURREAL_TEST_URL (and SURREAL_USER/SURREAL_PASS) to run the live SurrealDB test",
)
class TestSurrealIntegration(unittest.TestCase):
    """Exercises the SurrealDB-primary path against a live server when provided."""

    def test_memory_roundtrip_on_surrealdb(self):
        import tempfile

        from solomon_harness.tools.database_client import DatabaseClient

        # Scoped via patch.dict so SURREAL_URL is restored to its prior value (or
        # removed) on exit: an unconditional `os.environ[...] = ...` here leaked
        # into every test collected after this one in the same pytest session
        # (e.g. tests/test_memory.py's TestReadDbUrl), which only surfaced once
        # CI started setting SURREAL_TEST_URL and this class stopped skipping.
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"SURREAL_URL": os.environ["SURREAL_TEST_URL"]}),
        ):
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
