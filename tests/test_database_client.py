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
    TERMINAL_STATUSES,
    DatabaseClient,
    _resolve_database,
    is_github_issue,
    is_terminal,
    normalize_status,
    person_key_or_unassigned,
)


class TestIsGithubIssue(unittest.TestCase):
    def test_is_github_issue_classifies_by_digits_only(self):
        """is_github_issue is True only for a non-empty, ASCII, all-digits id, so a
        numeric GitHub id counts while a composite slug, empty, null, unicode-digit,
        or padded id is a tracking item (digits-only, not "contains a number")."""
        cases = {
            "116": True,
            "0": True,
            "116-R-01": False,
            "bug-x": False,
            "": False,
            None: False,
            "²": False,
            " 12 ": False,
        }
        for github_id, expected in cases.items():
            self.assertIs(is_github_issue(github_id), expected, msg=repr(github_id))


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
        # milestone_id is TEXT on both issues and releases (they share one type so
        # neither side needs a string-cast to compare), so it reads back as a string.
        self.assertEqual(issue["milestone_id"], str(milestone_id))

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
        # The legacy "pending" token normalizes to the canonical "open" at the
        # write seam (ADR-0016).
        self.assertEqual(handoff["status"], "open")

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

    def test_schema_bootstrap_raises_on_a_later_ddl_statement_failure(self):
        """A failure in any DEFINE statement -- not just the first -- must abort
        the SurrealDB schema bootstrap, so the backend is never marked "surrealdb"
        on a partially-applied schema (e.g. a missing HNSW vector index).

        The real surrealdb SDK's ``.query()`` only surfaces the FIRST statement's
        result when a multi-statement string is passed in one call, so a failure
        buried in a later statement is silently accepted. The mock below
        reproduces exactly that contract (it only inspects the first statement of
        whatever string it is given), which is what makes this test discriminate
        between the old single-call bootstrap (falsely reports success) and the
        fixed statement-by-statement bootstrap (the failing statement is index 0
        of its own call, so it is caught).
        """
        mock_surreal_class = MagicMock()
        mock_surreal_instance = MagicMock()
        mock_surreal_class.return_value = mock_surreal_instance

        def fails_if_first_statement_matches(marker):
            def _query(query_str, *args, **kwargs):
                statements = [s.strip() for s in query_str.split(";") if s.strip()]
                if statements and marker in statements[0]:
                    raise RuntimeError(f"simulated DDL failure: {statements[0][:60]}")
                return []

            return _query

        # The marker sits in the LAST schema statement (the HNSW vector index).
        mock_surreal_instance.query.side_effect = fails_if_first_statement_matches("HNSW")

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
            client = DatabaseClient()
            # A DDL failure anywhere in the schema must fail the bootstrap and
            # fall back to SQLite, never falsely report "surrealdb" as ready.
            self.assertEqual(client.backend, "sqlite")
            client.close()

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

        get_open_issues returns only non-terminal rows, but the cockpit board must
        render the full seven columns, so the read port needs an all-status read.
        Statuses are normalized on write (ADR-0006): In Progress -> in_progress and
        Done -> closed, while Backlog passes through unchanged.
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
            {"gh-1": "Backlog", "gh-2": "in_progress", "gh-3": "closed"},
        )

    def test_log_issue_normalizes_status_on_write(self):
        """log_issue collapses board display names and casing aliases to one
        canonical token per logical status, so no two rows differ only by casing."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        cases = {
            "In Progress": "in_progress",
            "in_progress": "in_progress",
            "Code Review": "code_review",
            "QA": "qa",
            "Done": "closed",
            "done": "closed",
            "closed": "closed",
            "Backlog": "Backlog",
            "open": "open",
        }
        for index, (written, expected) in enumerate(cases.items()):
            gid = f"norm-{index}"
            client.log_issue(gid, "Issue", "feature", written, None)
            self.assertEqual(client.get_issue(gid)["status"], expected)
        client.close()

    def test_get_open_issues_returns_non_terminal_rows(self):
        """get_open_issues is a non-terminal predicate, not a literal status='open'
        filter: it returns open/Backlog/in_progress and excludes closed/done."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("o1", "Open literal", "feature", "open", None)
        client.log_issue("o2", "Backlog item", "feature", "Backlog", None)
        client.log_issue("o3", "Active", "feature", "in_progress", None)
        client.log_issue("t1", "Closed", "feature", "closed", None)
        client.log_issue("t2", "Done token", "feature", "done", None)

        open_ids = {i["github_id"] for i in client.get_open_issues()}
        client.close()
        self.assertEqual(open_ids, {"o1", "o2", "o3"})

    def test_get_open_issues_excludes_legacy_unnormalized_terminal_rows(self):
        """The non-terminal predicate excludes legacy rows that carry done/Done
        verbatim (written before normalization), so the terminal-literal set has
        teeth on rows that bypass log_issue."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.executemany(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("L1", "legacy done", "bug", "done", None),
                    ("L2", "legacy Done", "bug", "Done", None),
                    ("L3", "legacy closed", "bug", "closed", None),
                ],
            )
            conn.commit()
        client.log_issue("o1", "Open one", "feature", "open", None)

        open_ids = {i["github_id"] for i in client.get_open_issues()}
        client.close()
        self.assertEqual(open_ids, {"o1"})

    def test_status_flip_to_terminal_leaves_no_duplicate_row(self):
        """A row flipped from any prior status to closed ends terminal, by
        github_id, with no duplicate row, and falls out of get_open_issues."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        priors = ["in_progress", "QA", "code_review", "Backlog", "open"]
        for prior in priors:
            gid = f"flip-{prior}"
            client.log_issue(gid, "Issue", "feature", prior, None)
            client.log_issue(gid, "Issue", "feature", "closed", None)
            self.assertEqual(client.get_issue(gid)["status"], "closed")

        ids = [r["github_id"] for r in client.list_issues() if r["github_id"].startswith("flip-")]
        open_ids = {i["github_id"] for i in client.get_open_issues()}
        client.close()

        self.assertEqual(len(ids), len(priors))  # one UPSERT row per id, no duplicates
        self.assertEqual(len(set(ids)), len(priors))
        self.assertEqual(open_ids & set(ids), set())

    def test_sqlite_stores_and_reads_assignee(self):
        """log_issue persists the canonical person key and get_issue reads it back
        on SQLite (the additive sixth parameter)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue(
            "a1", "Assigned", "feature", "open", None, assignee="alice@example.com"
        )
        issue = client.get_issue("a1")
        client.close()
        self.assertEqual(issue["assignee"], "alice@example.com")

    def test_five_arg_log_issue_stores_null_assignee(self):
        """An existing 5-arg log_issue caller keeps working unchanged and stores
        assignee=None (the additive parameter never breaks the old signature)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("five", "No assignee arg", "feature", "open", None)
        issue = client.get_issue("five")
        client.close()
        self.assertIsNone(issue["assignee"])

    def test_pre_migration_row_reads_back_unassigned(self):
        """A row written into an issues table that predates the assignee column
        reads back, after the additive ALTER TABLE migration, with assignee None
        and queryable as unassigned, with no error and no row rewrite."""
        db_path = os.path.join(self.temp_dir.name, "premigration.db")
        # Simulate a pre-migration store: a legacy issues table with no assignee.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE issues ("
                "github_id TEXT PRIMARY KEY, title TEXT NOT NULL, type_ TEXT, "
                "status TEXT, milestone_id INTEGER, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id) "
                "VALUES (?, ?, ?, ?, ?)",
                ("old1", "Legacy issue", "bug", "open", None),
            )
            conn.commit()
        # Opening the client runs the idempotent, additive assignee migration.
        client = DatabaseClient(db_path=db_path)
        issue = client.get_issue("old1")
        client.close()
        self.assertIsNone(issue["assignee"])
        self.assertEqual(person_key_or_unassigned(issue["assignee"]), "unassigned")

    def test_sqlite_issue_milestone_link_is_soft(self):
        """The issue -> milestone link is soft on SQLite too (ADR-0016).

        The FOREIGN KEY that used to target milestones.id (the integer rowid)
        rejected the client-minted milestone record ids that backend-invariant
        ids (F7) store in issues.milestone_id, so a rebuild migration dropped
        it. Both the minted spelling and a dangling reference are accepted,
        matching the SurrealDB primary, which never enforced one; the
        authoritative link is the graph ``contains`` edge.
        """
        client = DatabaseClient(db_path=self.sqlite_db_path)
        minted = client.create_milestone("M", "d", "2026-07-01", "open")
        client.log_issue("linked", "Linked", "feature", "open", minted)
        client.log_issue("orphan", "Orphaned", "bug", "open", 99999)
        linked = client.get_issue("linked")
        orphan = client.get_issue("orphan")
        client.close()
        assert linked is not None and orphan is not None
        self.assertEqual(linked["milestone_id"], str(minted))
        self.assertEqual(orphan["milestone_id"], "99999")

    def test_issues_milestone_id_column_is_text_matching_releases(self):
        """issues.milestone_id and releases.milestone_id share the same TEXT type,
        so a caller never needs a string-cast to compare them across tables."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("gh-text", "Item", "feature", "open", None)
        with sqlite3.connect(self.sqlite_db_path) as conn:
            columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(issues)")}
        client.close()
        self.assertEqual(columns["milestone_id"].upper(), "TEXT")

    def test_milestone_id_text_migration_preserves_existing_rows(self):
        """A pre-migration store with milestone_id INTEGER is migrated to TEXT in
        place, additively (#118-style expand/contract): existing rows, including
        their milestone_id value and any already-added assignee column, survive
        unchanged, and the store never raises during the migration."""
        db_path = os.path.join(self.temp_dir.name, "premigration_milestone.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE milestones (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "title TEXT NOT NULL, description TEXT, due_date TEXT, state TEXT, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO milestones (title, state) VALUES (?, ?)", ("M1", "active")
            )
            conn.execute(
                "CREATE TABLE issues (github_id TEXT PRIMARY KEY, title TEXT NOT NULL, "
                "type_ TEXT, status TEXT, milestone_id INTEGER, assignee TEXT, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id, "
                "assignee) VALUES (?, ?, ?, ?, ?, ?)",
                ("old1", "Legacy issue", "bug", "open", 1, "alice@example.com"),
            )
            conn.commit()

        client = DatabaseClient(db_path=db_path)
        issue = client.get_issue("old1")
        client.close()

        self.assertEqual(issue["milestone_id"], "1")
        self.assertEqual(issue["assignee"], "alice@example.com")
        with sqlite3.connect(db_path) as conn:
            columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(issues)")}
        self.assertEqual(columns["milestone_id"].upper(), "TEXT")

    def test_surreal_upsert_includes_assignee_field(self):
        """On SurrealDB the issue UPSERT CONTENT carries the assignee as a bound
        parameter, additively to the existing fields (mocked _run_surreal)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.backend = "surrealdb"
        captured = {}

        def fake_run(query, params=None):
            captured["query"] = query
            captured["params"] = params
            return []

        client._run_surreal = fake_run
        client.log_issue(
            "a1", "Assigned", "feature", "open", None, assignee="alice@example.com"
        )
        client.backend = "sqlite"
        client.close()

        self.assertIn("assignee: $assignee", captured["query"])
        self.assertEqual(captured["params"]["assignee"], "alice@example.com")

    def test_assignee_migration_is_idempotent_on_a_real_store(self):
        """Running the additive assignee migration twice on the same store is a
        no-op the second time (the PRAGMA guard short-circuits): it never raises
        and the column exists exactly once."""
        db_path = os.path.join(self.temp_dir.name, "idem.db")
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE issues (github_id TEXT PRIMARY KEY, title TEXT)")
            DatabaseClient._ensure_issue_assignee_column(conn)
            DatabaseClient._ensure_issue_assignee_column(conn)  # must not raise
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(issues)")]
        self.assertEqual(columns.count("assignee"), 1)

    def test_concurrent_duplicate_column_race_is_treated_as_migrated(self):
        """On the shared store two first-opens can both pass the PRAGMA guard before
        either ALTERs; the losing ALTER then raises 'duplicate column name'. The
        migration absorbs that as already-migrated and never raises."""

        class _RaceConn:
            """PRAGMA reports the column absent (guard passes), but the ALTER loses
            the race with a concurrent writer that already added it."""

            def execute(self, sql, *args):
                if sql.startswith("PRAGMA table_info"):
                    return [{"name": "github_id"}, {"name": "title"}]
                if sql.startswith("ALTER TABLE issues ADD COLUMN assignee"):
                    raise sqlite3.OperationalError("duplicate column name: assignee")
                raise AssertionError(f"unexpected sql: {sql}")

        DatabaseClient._ensure_issue_assignee_column(_RaceConn())  # must not raise

    def test_non_duplicate_alter_error_still_propagates(self):
        """A non-duplicate ALTER failure is a real error and must still propagate;
        the race guard absorbs only the duplicate-column case."""

        class _BrokenConn:
            def execute(self, sql, *args):
                if sql.startswith("PRAGMA table_info"):
                    return [{"name": "github_id"}]
                if sql.startswith("ALTER TABLE issues ADD COLUMN assignee"):
                    raise sqlite3.OperationalError("disk I/O error")
                raise AssertionError(f"unexpected sql: {sql}")

        with self.assertRaises(sqlite3.OperationalError):
            DatabaseClient._ensure_issue_assignee_column(_BrokenConn())

    def test_sqlite_write_error_logs_type_only_not_message(self):
        """A SQLite issue-write failure logs the exception type and record id, never
        str(e). The issue row now carries the person key (an email when public), so a
        backend error string must not leak it into logs (STRIDE: info disclosure)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        secret = "alice@example.com"
        fields = {
            "github_id": "issue-1", "title": "T", "type_": "bug",
            "status": "open", "milestone_id": None, "assignee": secret,
        }
        with patch.object(
            client, "_sqlite_conn",
            side_effect=sqlite3.OperationalError(f"disk error near {secret}"),
        ):
            with self.assertLogs(level="ERROR") as logs:
                with self.assertRaises(RuntimeError):
                    client._db_log_issue("issue-1", fields)
        client.close()
        joined = "\n".join(logs.output)
        self.assertIn("OperationalError", joined)  # the exception type is logged
        self.assertIn("issue-1", joined)  # and the record id
        self.assertNotIn(secret, joined)  # but never the message (no person key leak)

    def test_surreal_write_error_logs_type_only_not_message(self):
        """The SurrealDB issue-write branch logs the exception type and record id,
        never str(e), so a backend error string cannot leak the person key."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.backend = "surrealdb"
        secret = "alice@example.com"

        def boom(query, params=None):
            raise ValueError(f"surreal blew up on {secret}")

        client._run_surreal = boom
        fields = {
            "github_id": "issue-9", "title": "T", "type_": "bug",
            "status": "open", "milestone_id": None, "assignee": secret,
        }
        with self.assertLogs(level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                client._db_log_issue("issue-9", fields)
        client.backend = "sqlite"
        client.close()
        joined = "\n".join(logs.output)
        self.assertIn("ValueError", joined)  # the exception type is logged
        self.assertIn("issue-9", joined)  # and the record id
        self.assertNotIn(secret, joined)  # but never the message (no person key leak)

    def test_get_open_issues_surreal_uses_parameterized_not_in(self):
        """On SurrealDB the open predicate is a parameterized NOT IN over the
        terminal-literal set, never a string-interpolated literal (STRIDE)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.backend = "surrealdb"
        captured = {}

        def fake_run(query, params=None):
            captured["query"] = query
            captured["params"] = params
            return []

        client._run_surreal = fake_run
        client.get_open_issues()
        client.backend = "sqlite"
        client.close()

        self.assertIn("NOT IN", captured["query"])
        self.assertEqual(captured["params"], {"terminal": list(TERMINAL_STATUSES)})

    def test_get_open_issues_keeps_null_status_rows_sqlite(self):
        """A row with no status is non-terminal and kept by get_open_issues, matching
        is_terminal(None) being False and digest.build_digest, so the two consumers
        agree on null-status rows. A bare SQL NOT IN would drop a NULL row."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.log_issue("n1", "No status", "feature", None, None)
        client.log_issue("t1", "Closed", "feature", "closed", None)

        open_ids = {i["github_id"] for i in client.get_open_issues()}
        client.close()
        self.assertIn("n1", open_ids)
        self.assertNotIn("t1", open_ids)

    def test_get_open_issues_annotates_github_vs_tracking(self):
        """get_open_issues annotates each non-terminal row with a derived
        is_github_issue boolean, so a numeric GitHub id (116) is True while a
        composite RAID slug (116-R-01) and an empty id are tracking (False). The
        annotation is additive: it never changes which rows are returned."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.executemany(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("116", "Numeric GitHub issue", "feature", "in_progress", None),
                    ("116-R-01", "RAID follow-up", "task", "open", None),
                    ("", "Empty id tracking", "task", None, None),
                ],
            )
            conn.commit()

        annotated = {row["github_id"]: row["is_github_issue"] for row in client.get_open_issues()}
        client.close()
        self.assertIs(annotated["116"], True)
        self.assertIs(annotated["116-R-01"], False)
        self.assertIs(annotated[""], False)

    def test_get_open_issues_predicate_unchanged_after_annotation(self):
        """The bucket annotation changed no row membership: get_open_issues still
        returns exactly the non-terminal set, and a terminal numeric id (999,
        closed) never leaks into the GitHub bucket. Pins that the {closed, done,
        Done} predicate (ADR-0006) is unchanged in meaning after the annotation."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.executemany(
                "INSERT INTO issues (github_id, title, type_, status, milestone_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("116", "Numeric open", "feature", "in_progress", None),
                    ("116-R-01", "Composite open", "task", "open", None),
                    ("n1", "Null status", "task", None, None),
                    ("999", "Terminal numeric", "feature", "closed", None),
                    ("L1", "Legacy terminal", "bug", "Done", None),
                ],
            )
            conn.commit()

        rows = client.get_open_issues()
        client.close()
        returned = {row["github_id"] for row in rows}
        github_bucket = {row["github_id"] for row in rows if row["is_github_issue"]}
        self.assertEqual(returned, {"116", "116-R-01", "n1"})
        self.assertNotIn("999", returned)
        self.assertNotIn("999", github_bucket)
        self.assertEqual(github_bucket, {"116"})

    def test_get_open_issues_surreal_query_tolerates_null_status(self):
        """On SurrealDB the open predicate keeps NULL/NONE-status rows (consistent
        with is_terminal(None) being False), still binding the terminal set as a
        parameter rather than string-formatting it (STRIDE)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.backend = "surrealdb"
        captured = {}

        def fake_run(query, params=None):
            captured["query"] = query
            captured["params"] = params
            return []

        client._run_surreal = fake_run
        client.get_open_issues()
        client.backend = "sqlite"
        client.close()

        self.assertIn("NOT IN", captured["query"])
        self.assertIn("NONE", captured["query"].upper())
        self.assertEqual(captured["params"], {"terminal": list(TERMINAL_STATUSES)})

    def test_status_vocabulary_helpers(self):
        """normalize_status and is_terminal agree on the canonical vocabulary."""
        self.assertEqual(normalize_status("In Progress"), "in_progress")
        self.assertEqual(normalize_status("Code Review"), "code_review")
        self.assertEqual(normalize_status("Done"), "closed")
        self.assertEqual(normalize_status("open"), "open")
        self.assertIsNone(normalize_status(None))
        # The review/QA end of the vocabulary: unreachable in practice until #173
        # ungated the write-through, so assert the tokens explicitly.
        self.assertEqual(normalize_status("QA"), "qa")
        self.assertEqual(normalize_status("qa"), "qa")
        self.assertEqual(normalize_status("code_review"), "code_review")
        # The legacy word an early stage wrote, retired by the #173 pass.
        self.assertEqual(normalize_status("review"), "code_review")
        self.assertEqual(normalize_status("backlog"), "Backlog")
        self.assertTrue(is_terminal("closed"))
        self.assertTrue(is_terminal("done"))
        self.assertTrue(is_terminal("Done"))
        self.assertFalse(is_terminal("in_progress"))
        self.assertFalse(is_terminal("open"))
        self.assertFalse(is_terminal(None))

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

    def test_get_memory_bulk_sqlite(self):
        """get_memory_bulk returns every stored key's value in one call, and a
        key that was never saved is simply absent from the result (never a
        raise, never a None placeholder)."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        client.save_memory("bh:1", "one", "board_history")
        client.save_memory("bh:2", "two", "board_history")
        client.save_memory("bh:3", "three", "board_history")

        result = client.get_memory_bulk(["bh:1", "bh:2", "bh:missing"])

        self.assertEqual(result, {"bh:1": "one", "bh:2": "two"})
        self.assertNotIn("bh:missing", result)
        client.close()

    def test_get_memory_bulk_empty_keys_is_a_no_op(self):
        """get_memory_bulk on an empty key list returns an empty dict without
        issuing any query."""
        client = DatabaseClient(db_path=self.sqlite_db_path)
        self.assertEqual(client.get_memory_bulk([]), {})
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


class TestBoardColumnsSingleSource(unittest.TestCase):
    """The delivery-board column names have one canonical definition (ADR-0006).

    Fitness function: the display-column values of the status vocabulary and the
    BOARD_COLUMNS list must stay in lockstep, and every consumer must import the
    one definition rather than re-declaring it, so the names cannot drift.
    """

    def test_display_columns_match_board_columns(self):
        from solomon_harness.tools.database_client import (
            BOARD_COLUMNS,
            STATUS_DISPLAY_COLUMNS,
        )

        self.assertEqual(set(STATUS_DISPLAY_COLUMNS.values()), set(BOARD_COLUMNS))

    def test_board_columns_order_is_canonical(self):
        from solomon_harness.tools.database_client import BOARD_COLUMNS

        self.assertEqual(
            BOARD_COLUMNS,
            ["Ideas", "Backlog", "Ready", "In Progress", "Code Review", "QA", "Done"],
        )

    def test_consumers_share_the_one_board_columns_object(self):
        from solomon_harness import cockpit_read, github
        from solomon_harness.tools import database_client

        self.assertIs(github.BOARD_COLUMNS, database_client.BOARD_COLUMNS)
        self.assertIs(cockpit_read.BOARD_COLUMNS, database_client.BOARD_COLUMNS)


if __name__ == "__main__":
    unittest.main()
