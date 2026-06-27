import unittest
import os
import sys
import tempfile
import json
import builtins
import io
from unittest.mock import MagicMock, patch

# Ensure the template harness path is in sys.path
harness_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates", "harness"))
if harness_path not in sys.path:
    sys.path.insert(0, harness_path)

from tools.database_client import DatabaseClient


class TestDatabaseClient(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for SQLite DB files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
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
            commit_sha="abc1234"
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
            state="active"
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
            milestone_id=milestone_id
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
            commit_sha="abc1234"
        )
        self.assertIsNotNone(backtest_id)
        
        backtest = client.get_backtest(backtest_id)
        self.assertIsNotNone(backtest)
        self.assertEqual(backtest["strategy_name"], "EMA_Cross")
        self.assertEqual(backtest["sharpe_ratio"], 1.5)

        # Test save_session and get_session
        test_messages = [{"role": "user", "content": "hello"}, {"role": "agent", "content": "hi"}]
        client.save_session(
            session_id="sess-123",
            agent_name="product_owner",
            task="Refactor DB client",
            messages=test_messages
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
            status="pending"
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
                "password": "root"
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

        with patch("builtins.__import__", side_effect=mock_import), \
             patch("os.path.isfile", side_effect=mock_isfile), \
             patch("builtins.open", side_effect=mock_open):
            
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
                "password": "root"
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

        with patch("builtins.__import__", side_effect=mock_import), \
             patch("os.path.isfile", side_effect=mock_isfile), \
             patch("builtins.open", side_effect=mock_open):
                
            client = DatabaseClient(db_path=self.sqlite_db_path)
            self.assertEqual(client.backend, "surrealdb")
            
            # Verify SurrealDB setup calls
            mock_surreal_class.assert_called_once_with("ws://localhost:8000/rpc")
            mock_surreal_instance.connect.assert_called_once()
            mock_surreal_instance.signin.assert_called_once_with({"user": "root", "pass": "root"})
            mock_surreal_instance.use.assert_called_once_with("solomon", "harness")
            
            # Verify initialization queries
            mock_surreal_instance.query.assert_called()
            
            # Reset mock for method calls
            mock_surreal_instance.query.reset_mock()
            
            # 1. log_decision
            mock_surreal_instance.query.return_value = [[{"id": "decisions:1"}]]
            decision_id = client.log_decision("Title", "Rationale", "Outcome", "Author", "branch", "sha")
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
            bt_id = client.save_backtest("Strategy", 1.2, 0.1, 1.5, "{}", "Dataset", "sha")
            self.assertEqual(bt_id, "backtest_runs:1")

            # 7. save_session
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = []
            client.save_session("sess-123", "agent", "task", [{"role": "user", "content": "hi"}])
            mock_surreal_instance.query.assert_called_once()

            # 8. get_session
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"session_id": "sess-123", "agent_name": "agent", "task": "task", "messages": [{"role": "user", "content": "hi"}]}]]
            sess = client.get_session("sess-123")
            self.assertIsNotNone(sess)
            self.assertEqual(sess["session_id"], "sess-123")

            # 9. log_handoff
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"id": "handoffs:1"}]]
            handoff_id = client.log_handoff("sender", "recipient", "plan", "/path", "pending")
            self.assertEqual(handoff_id, "handoffs:1")

            # 10. get_handoff
            mock_surreal_instance.query.reset_mock()
            mock_surreal_instance.query.return_value = [[{"id": "handoffs:1", "sender": "sender", "recipient": "recipient"}]]
            handoff = client.get_handoff("handoffs:1")
            self.assertIsNotNone(handoff)
            self.assertEqual(handoff["sender"], "sender")
            
            # 11. Close client / context manager
            client.close()
            mock_surreal_instance.close.assert_called_once()

    def test_project_root_resolution_with_git(self):
        """Test unified project root directory resolution when .git is found."""
        with patch("tools.database_client.__file__", "/mock/repo/templates/harness/tools/database_client.py"), \
             patch("os.path.exists") as mock_exists, \
             patch("os.path.isfile") as mock_isfile, \
             patch("os.makedirs") as mock_makedirs, \
             patch("sqlite3.connect") as mock_connect:
            
            def side_effect_exists(path):
                if path == "/mock/repo/.git":
                    return True
                return False
                
            mock_exists.side_effect = side_effect_exists
            mock_isfile.return_value = False
            
            client = DatabaseClient()
            self.assertEqual(client.db_path, "/mock/repo/memory/long_term/harness.db")
            client.close()

    def test_project_root_resolution_fallback(self):
        """Test unified project root directory fallback when no .git is found."""
        with patch("tools.database_client.__file__", "/mock/repo/templates/harness/tools/database_client.py"), \
             patch("os.path.exists") as mock_exists, \
             patch("os.path.isfile") as mock_isfile, \
             patch("os.makedirs") as mock_makedirs, \
             patch("sqlite3.connect") as mock_connect:
            
            mock_exists.return_value = False
            mock_isfile.return_value = False
            
            client = DatabaseClient()
            self.assertEqual(client.db_path, "/mock/repo/templates/harness/memory/long_term/harness.db")
            client.close()


if __name__ == "__main__":
    unittest.main()
