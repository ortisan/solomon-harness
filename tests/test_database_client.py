import unittest
import os
import sys
import tempfile
import json
import builtins
import io
import sqlite3
from unittest.mock import MagicMock, patch

# Ensure the repository root is on sys.path so the package imports cleanly.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    DatabaseClient,
    _resolve_database,
)


class TestResolveDatabase(unittest.TestCase):
    def test_generic_sentinel_derives_owner_repo_tenant(self):
        with patch("solomon_harness.home.derive_tenant", return_value="acme-widget"):
            self.assertEqual(_resolve_database("harness", "/repo"), "acme-widget")
            self.assertEqual(_resolve_database("", "/repo"), "acme-widget")
            self.assertEqual(_resolve_database(None, "/repo"), "acme-widget")

    def test_explicit_name_is_kept(self):
        with patch("solomon_harness.home.derive_tenant", return_value="acme-widget"):
            self.assertEqual(_resolve_database("custom_db", "/repo"), "custom_db")

    def test_falls_back_to_harness_when_derivation_fails(self):
        with patch("solomon_harness.home.derive_tenant", side_effect=RuntimeError):
            self.assertEqual(_resolve_database("harness", "/repo"), "harness")


class TestDatabaseClient(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for SQLite DB files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_db_path = os.path.join(self.temp_dir.name, "harness.db")
        # Keep the write-through mirror (#35) inside the temp dir so the SurrealDB
        # tests here (built without a db_path) never touch the real project's
        # .solomon/ store.
        self._mirror_env = patch.dict(
            os.environ, {"HARNESS_MIRROR_ROOT": os.path.join(self.temp_dir.name, "mirror")}
        )
        self._mirror_env.start()

    def tearDown(self):
        self._mirror_env.stop()
        self.temp_dir.cleanup()

    def test_sqlite_backend_initialization_and_operations(self):
        """Test that the client initializes and performs operations with SQLite backend."""
        client = DatabaseClient(db_path=self.sqlite_db_path)

        # Test log_decision
        decision_id = client.log_decision(
            title="Design Decision",
            rationale="Use SQLite fallback",
            outcome="Approved",
            author="Agent",
            branch="main",
            commit_sha="abc1234",
        )
        self.assertIsNotNone(decision_id)

        decision = client.get_decision(decision_id)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["title"], "Design Decision")
        self.assertEqual(decision["rationale"], "Use SQLite fallback")

        # Test save_memory and get_memory
        client.save_memory("test_key", "test_value", "test_cat")
        val = client.get_memory("test_key")
        self.assertEqual(val, "test_value")

        # Test create_milestone and get_milestone
        milestone_id = client.create_milestone(
            title="Milestone 1",
            description="First milestone",
            due_date="2026-07-01",
            state="active",
        )
        self.assertIsNotNone(milestone_id)

        milestone = client.get_milestone(milestone_id)
        self.assertIsNotNone(milestone)
        self.assertEqual(milestone["title"], "Milestone 1")

        # Test log_issue and get_issue
        client.log_issue(
            github_id="gh-42",
            title="Issue 42",
            type_="bug",
            status="open",
            milestone_id=milestone_id,
        )
        issue = client.get_issue("gh-42")
        self.assertIsNotNone(issue)
        self.assertEqual(issue["title"], "Issue 42")
        self.assertEqual(issue["milestone_id"], milestone_id)

        # Test save_backtest and get_backtest
        backtest_id = client.save_backtest(
            strategy_name="EMA_Cross",
            sharpe_ratio=1.5,
            max_drawdown=0.15,
            profit_factor=1.8,
            parameters='{"fast": 10, "slow": 20}',
            dataset="BTCUSDT",
            commit_sha="abc1234",
        )
        self.assertIsNotNone(backtest_id)

        backtest = client.get_backtest(backtest_id)
        self.assertIsNotNone(backtest)
        self.assertEqual(backtest["strategy_name"], "EMA_Cross")
        self.assertEqual(backtest["sharpe_ratio"], 1.5)

        # Test save_session and get_session
        test_messages = [
            {"role": "user", "content": "hello"},
            {"role": "agent", "content": "hi"},
        ]
        client.save_session(
            session_id="sess-123",
            agent_name="product_owner",
            task="Refactor DB client",
            messages=test_messages,
        )
        session = client.get_session("sess-123")
        self.assertIsNotNone(session)
        self.assertEqual(session["agent_name"], "product_owner")
        self.assertEqual(session["task"], "Refactor DB client")

        retrieved_msgs = session["messages"]
        if isinstance(retrieved_msgs, str):
            retrieved_msgs = json.loads(retrieved_msgs)
        self.assertEqual(retrieved_msgs[0]["content"], "hello")

        # Test log_handoff and get_handoff
        handoff_id = client.log_handoff(
            sender="product_owner",
            recipient="scrum_master",
            contract_type="plan",
            contract_path="/some/path/plan.md",
            status="pending",
        )
        self.assertIsNotNone(handoff_id)

        handoff = client.get_handoff(handoff_id)
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff["sender"], "product_owner")
        self.assertEqual(handoff["recipient"], "scrum_master")
        self.assertEqual(handoff["status"], "pending")

        client.close()

    def test_surrealdb_backend_fallback_on_missing_library(self):
        """Test that the client falls back to SQLite when surrealdb package is missing."""
        config_data = {
            "database": {
                "provider": "surrealdb",
                "url": "ws://localhost:8000/rpc",
                "namespace": "solomon",
                "database": "harness",
                "username": "root",
                "password": "root",
            }
        }

        # Mock imports to raise ImportError for surrealdb
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "surrealdb":
                raise ImportError("Mocked missing library")
            return original_import(name, *args, **kwargs)

        def mock_isfile(path):
            if path.endswith("config.json"):
                return True
            return os.path.isfile(path)

        original_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if str(path).endswith("config.json"):
                return io.StringIO(json.dumps(config_data))
            return original_open(path, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch("os.path.isfile", side_effect=mock_isfile),
            patch("builtins.open", side_effect=mock_open),
        ):
            client = DatabaseClient(db_path=self.sqlite_db_path)
            self.assertEqual(client.backend, "sqlite")

            # Verify SQLite operations still work as fallback
            client.save_memory("fallback_key", "fallback_val", "test")
            self.assertEqual(client.get_memory("fallback_key"), "fallback_val")
            client.close()

    def test_surrealdb_backend_working_correctly(self):
        """Test that the client connects to SurrealDB when configured and package is available."""
        mock_surreal_class = MagicMock()
        mock_surreal_instance = MagicMock()
        mock_surreal_class.return_value = mock_surreal_instance
        mock_surreal_instance.query.return_value = []

        config_data = {
            "database": {
                "provider": "surrealdb",
                "url": "ws://localhost:8000/rpc",
                "namespace": "solomon",
                "database": "harness",
                "username": "root",
                "password": "root",
            }
        }

        mock_surrealdb = MagicMock()
        mock_surrealdb.Surreal = mock_surreal_class

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "surrealdb":
                return mock_surrealdb
            return original_import(name, *args, **kwargs)

        def mock_isfile(path):
            if path.endswith("config.json"):
                return True
            return os.path.isfile(path)

        original_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if str(path).endswith("config.json"):
                return io.StringIO(json.dumps(config_data))
            return original_open(path, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch("os.path.isfile", side_effect=mock_isfile),
            patch("builtins.open", side_effect=mock_open),
            patch("solomon_harness.home.derive_tenant", return_value="acme-widget"),
        ):
            # No db_path: an explicit db_path now forces SQLite, so the SurrealDB
            # path is exercised via config resolution instead.
            client = DatabaseClient()
            self.assertEqual(client.backend, "surrealdb")

            # Verify SurrealDB setup calls
            mock_surreal_class.assert_called_once_with("ws://localhost:8000/rpc")
            mock_surreal_instance.connect.assert_called_once()
            mock_surreal_instance.signin.assert_called_once_with(
                {"username": "root", "password": "root"}
            )
            # The generic "harness" config name is resolved to the <owner>-<repo>
            # tenant so projects never collide in the shared SurrealDB.
            mock_surreal_instance.use.assert_called_once_with("solomon", "acme-widget")

            # Verify initialization queries
            mock_surreal_instance.query.assert_called()

            # Reset mock for method calls
            mock_surreal_instance.query.reset_mock()

            # 1. log_decision
            mock_surreal_instance.query.return_value = [[{"id": "decisions:1"}]]
            decision_id = client.log_decision(
                "Title", "Rationale", "Outcome", "Author", "branch", "sha"
            )
            self.assertEqual(decision_id, "decisions:1")
            mock_surreal_instance.query.assert_called_once()

            # 2. save_memory
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = []
            client.save_memory("key", "val", "cat")
            mock_surreal_instance.query.assert_called_once()

            # 3. get_memory
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"value": "val"}]]
            val = client.get_memory("key")
            self.assertEqual(val, "val")

            # 4. create_milestone
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"id": "milestones:1"}]]
            milestone_id = client.create_milestone("M1", "Desc", "2026", "active")
            self.assertEqual(milestone_id, "milestones:1")

            # 5. log_issue
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = []
            client.log_issue("gh-1", "Title", "bug", "open", "milestones:1")
            mock_surreal_instance.query.assert_called_once()

            # 6. save_backtest
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"id": "backtest_runs:1"}]]
            bt_id = client.save_backtest(
                "Strategy", 1.2, 0.1, 1.5, "{}", "Dataset", "sha"
            )
            self.assertEqual(bt_id, "backtest_runs:1")

            # 7. save_session
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = []
            client.save_session(
                "sess-123", "agent", "task", [{"role": "user", "content": "hi"}]
            )
            mock_surreal_instance.query.assert_called_once()

            # 8. get_session
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [
                [
                    {
                        "session_id": "sess-123",
                        "agent_name": "agent",
                        "task": "task",
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ]
            ]
            sess = client.get_session("sess-123")
            self.assertIsNotNone(sess)
            self.assertEqual(sess["session_id"], "sess-123")

            # 9. log_handoff
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"id": "handoffs:1"}]]
            handoff_id = client.log_handoff(
                "sender", "recipient", "plan", "/path", "pending"
            )
            self.assertEqual(handoff_id, "handoffs:1")

            # 10. get_handoff
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [
                [{"id": "handoffs:1", "sender": "sender", "recipient": "recipient"}]
            ]
            handoff = client.get_handoff("handoffs:1")
            self.assertIsNotNone(handoff)
            self.assertEqual(handoff["sender"], "sender")

            # 11. list_databases reads tenant names from INFO FOR NS, sorted.
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [
                {
                    "databases": {
                        "beta": "DEFINE DATABASE beta",
                        "alpha": "DEFINE DATABASE alpha",
                    }
                }
            ]
            self.assertEqual(client.list_databases(), ["alpha", "beta"])

            # A missing/empty databases map yields no tenants, not an error.
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [{"tables": {}}]
            self.assertEqual(client.list_databases(), [])

            # 12. list_issues returns every row including Done (not just open).
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [
                [
                    {"github_id": "gh-1", "status": "Backlog"},
                    {"github_id": "gh-2", "status": "Done"},
                ]
            ]
            issues = client.list_issues()
            self.assertEqual(
                {i["github_id"]: i["status"] for i in issues},
                {"gh-1": "Backlog", "gh-2": "Done"},
            )

            # 13. use_tenant re-scopes the open connection to the selected tenant
            # via the SDK's parameterized bind (read-only, no SQL, one database).
            mock_surreal_instance.use.reset_mock()
            client.use_tenant("beta")
            mock_surreal_instance.use.assert_called_once_with("solomon", "beta")

            # 14. Close client / context manager
            client.close()
            mock_surreal_instance.close.assert_called_once()

    def test_spectron_initialization_and_usage(self):
        """Test that the client initializes Spectron when configured and routes calls through it."""
        mock_surreal_class = MagicMock()
        mock_surreal_instance = MagicMock()
        mock_surreal_class.return_value = mock_surreal_instance
        mock_surreal_instance.query.return_value = []

        mock_spectron_class = MagicMock()
        mock_spectron_instance = MagicMock()
        mock_spectron_class.return_value = mock_spectron_instance

        config_data = {
            "database": {
                "provider": "surrealdb",
                "url": "ws://localhost:8000/rpc",
                "namespace": "solomon",
                "database": "harness",
                "username": "root",
                "password": "root",
                "spectron_url": "http://localhost:9090",
                "spectron_api_key": "sk_test_key",
                "spectron_context": "test-context"
            }
        }

        mock_surrealdb = MagicMock()
        mock_surrealdb.Surreal = mock_surreal_class
        mock_surrealdb.Spectron = mock_spectron_class

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "surrealdb":
                return mock_surrealdb
            return original_import(name, *args, **kwargs)

        def mock_isfile(path):
            if path.endswith("config.json"):
                return True
            return os.path.isfile(path)

        original_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if str(path).endswith("config.json"):
                return io.StringIO(json.dumps(config_data))
            return original_open(path, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch("os.path.isfile", side_effect=mock_isfile),
            patch("builtins.open", side_effect=mock_open),
        ):
            # No db_path: see note in test_surrealdb_backend_working_correctly.
            client = DatabaseClient()
            self.assertEqual(client.backend, "surrealdb")
            self.assertIsNotNone(client.spectron)

            # Verify Spectron client initialization
            mock_spectron_class.assert_called_once_with(
                context="test-context",
                endpoint="http://localhost:9090",
                api_key="sk_test_key"
            )

            # Test save_memory routes through Spectron
            client.save_memory("mykey", "myval", "mycat")
            mock_spectron_instance.remember.assert_called_once_with(
                fact="myval", scope=["mycat", "mykey"]
            )

            # Test get_memory routes through Spectron
            mock_hit = MagicMock()
            mock_hit.text = "myval"
            mock_spectron_instance.recall.return_value = MagicMock(hits=[mock_hit])
            
            val = client.get_memory("mykey")
            self.assertEqual(val, "myval")
            mock_spectron_instance.recall.assert_called_once_with("mykey")

            client.close()

    def test_project_root_resolution_with_git(self):
        """Project root resolves to the nearest ancestor containing .git."""
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.path.isfile") as mock_isfile,
            patch("os.makedirs"),
            patch("sqlite3.connect"),
        ):

            def side_effect_exists(path):
                if path == "/mock/repo/.git":
                    return True
                return False

            mock_exists.side_effect = side_effect_exists
            mock_isfile.return_value = False

            client = DatabaseClient(harness_dir="/mock/repo/templates/harness")
            self.assertEqual(client.db_path, "/mock/repo/memory/long_term/harness.db")
            client.close()

    def test_project_root_resolution_fallback(self):
        """Project root falls back to the harness directory when no root is found."""
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.path.isfile") as mock_isfile,
            patch("os.makedirs"),
            patch("sqlite3.connect"),
        ):
            mock_exists.return_value = False
            mock_isfile.return_value = False

            client = DatabaseClient(harness_dir="/mock/repo/templates/harness")
            self.assertEqual(
                client.db_path,
                "/mock/repo/templates/harness/memory/long_term/harness.db",
            )
            client.close()

    def test_project_root_resolution_inside_agent_without_git(self):
        """Project root resolves via workspace markers when run from an agent dir."""
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.path.isfile") as mock_isfile,
            patch("os.makedirs"),
            patch("sqlite3.connect"),
        ):

            def side_effect_exists(path):
                if path in [
                    "/mock/repo/agents",
                    "/mock/repo/memory",
                    "/mock/repo/solomon_harness",
                ]:
                    return True
                return False
            mock_exists.side_effect = side_effect_exists
            mock_isfile.return_value = False

            client = DatabaseClient(harness_dir="/mock/repo/agents/documenter")
            self.assertEqual(client.db_path, "/mock/repo/memory/long_term/harness.db")
            client.close()

    def test_reads_harness_local_config_not_repo_root(self):
        """The client must read the harness-local .agent/config.json (which carries the
        database block), not the repo-root config that lacks one."""
        root = self.temp_dir.name
        os.makedirs(os.path.join(root, ".git"))
        os.makedirs(os.path.join(root, ".agent"))
        with open(os.path.join(root, ".agent", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"models": {"default": "x"}}, f)  # repo root: no database block

        harness = os.path.join(root, "agents", "qa")
        os.makedirs(os.path.join(harness, ".agent"))
        with open(
            os.path.join(harness, ".agent", "config.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "agent_name": "qa",
                    "database": {
                        "provider": "surrealdb",
                        "url": "ws://harness-local:8000/rpc",
                        "namespace": "solomon",
                        "database": "harness",
                        # Non-local URL requires explicit credentials (fail-closed).
                        "username": "qa_user",
                        "password": "qa_pass",
                    },
                },
                f,
            )

        mock_instance = MagicMock()
        mock_instance.query.return_value = []
        mock_class = MagicMock(return_value=mock_instance)
        mock_surrealdb = MagicMock()
        mock_surrealdb.Surreal = mock_class

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "surrealdb":
                return mock_surrealdb
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            client = DatabaseClient(harness_dir=harness)
            self.assertEqual(client.backend, "surrealdb")
            mock_class.assert_called_once_with("ws://harness-local:8000/rpc")
            client.close()

    def test_releases_and_milestones_listing_sqlite(self):
        """Milestones and delivered releases are recorded and listable."""
        client = DatabaseClient(db_path=self.sqlite_db_path)

        m1 = client.create_milestone("M1", "first", "2026-07-01", "active")
        m2 = client.create_milestone("M2", "second", "2026-08-01", "active")
        milestones = client.list_milestones()
        self.assertEqual({m["title"] for m in milestones}, {"M1", "M2"})

        rid = client.save_release(
            version="v1.0.0",
            tag="v1.0.0",
            notes="Initial release",
            issue_github_id="42",
            milestone_id=m1,
            commit_sha="abc1234",
        )
        self.assertIsNotNone(rid)
        rel = client.get_release(rid)
        self.assertEqual(rel["version"], "v1.0.0")
        self.assertEqual(rel["issue_github_id"], "42")
        self.assertEqual(rel["milestone_id"], str(m1))

        client.save_release(version="v1.1.0", tag="v1.1.0", milestone_id=m2)
        releases = client.list_releases()
        self.assertEqual(len(releases), 2)
        self.assertEqual({r["version"] for r in releases}, {"v1.0.0", "v1.1.0"})
        client.close()

    def test_list_issues_returns_all_statuses_including_done(self):
        """list_issues returns every issue regardless of status, including Done.

        get_open_issues only returns status='open', but the cockpit board must
        render the full seven columns, so the read port needs an all-status read.
        """
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("gh-1", "Backlog item", "feature", "Backlog", None)
        client.log_issue("gh-2", "Active item", "feature", "In Progress", None)
        client.log_issue("gh-3", "Shipped item", "feature", "Done", None)

        issues = client.list_issues()
        client.close()

        by_id = {i["github_id"]: i["status"] for i in issues}
        self.assertEqual(
            by_id,
            {"gh-1": "Backlog", "gh-2": "In Progress", "gh-3": "Done"},
        )

    def test_list_databases_is_read_only(self):
        """list_databases discovers the tenant(s) without mutating the store.

        On the SQLite fallback it returns the single resolvable tenant; the call
        must create or change no row.
        """
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("gh-1", "Item", "feature", "Backlog", None)
        before = client.list_issues()

        tenants = client.list_databases()

        after = client.list_issues()
        client.close()

        self.assertIsInstance(tenants, list)
        self.assertGreaterEqual(len(tenants), 1)
        self.assertTrue(all(isinstance(t, str) for t in tenants))
        self.assertEqual(before, after)

    def test_delete_memory_sqlite(self):
        """delete_memory removes a key so get_memory returns None afterwards."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.save_memory("doomed", "value", "test")
        self.assertEqual(client.get_memory("doomed"), "value")
        client.delete_memory("doomed")
        self.assertIsNone(client.get_memory("doomed"))
        # Deleting a missing key must be a no-op, not an error.
        client.delete_memory("never_existed")
        client.close()

    def test_sqlite_uses_wal(self):
        """SQLite connections must run in WAL journal mode so the shared store is safe
        for concurrent agents."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.save_memory("k", "v", "c")
        client.close()

        conn = sqlite3.connect(self.sqlite_db_path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(mode.lower(), "wal")


if __name__ == "__main__":
    unittest.main()
