import unittest
import os
import sys
import json
import tempfile
import unicodedata
from unittest.mock import MagicMock, patch

# Dynamically locate the parent agent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import DatabaseClient and main module
try:
    from tools.database_client import DatabaseClient
except ImportError:
    DatabaseClient = None

import main


class TestAgentEvals(unittest.TestCase):
    """Unit tests for verifying agent files, configurations, and runner loop."""

    def setUp(self) -> None:
        self.parent_dir = parent_dir
        self.cliches = [
            "delve",
            "leverage",
            "testament",
            "dive into",
            "feel free",
            "in summary",
            "moreover",
            "firstly",
            "secondly",
            "lastly"
        ]
        # Set up a temporary directory and database path for isolation
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_db_path = os.path.join(self.temp_dir.name, "harness_test.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _has_emoji(self, text: str) -> tuple[bool, str | None]:
        for char in text:
            cp = ord(char)
            is_emoji = (0x1F000 <= cp <= 0x1FFFF) or (0x2600 <= cp <= 0x27BF) or (0x2300 <= cp <= 0x23FF)
            if not is_emoji:
                try:
                    cat = unicodedata.category(char)
                    if cat == 'So':
                        is_emoji = True
                    else:
                        name = unicodedata.name(char, "").upper()
                        if any(word in name for word in ("EMOJI", "SMILEY", "PICTOGRAPH")):
                            is_emoji = True
                except Exception:
                    pass
            if is_emoji:
                return True, char
        return False, None

    def test_persona_markdown(self) -> None:
        """Validate that the agent persona markdown file has no emojis or AI cliches."""
        persona_path = os.path.join(self.parent_dir, "persona.md")
        self.assertTrue(os.path.isfile(persona_path), f"persona.md not found at {persona_path}")

        with open(persona_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for emojis
        emoji_found, emoji_char = self._has_emoji(content)
        self.assertFalse(emoji_found, f"Emoji or icon '{emoji_char}' found in persona.md.")

        # Check for AI cliches
        content_lower = content.lower()
        for cliche in self.cliches:
            self.assertNotIn(cliche, content_lower, f"AI cliche '{cliche}' found in persona.md.")

    def test_config_json(self) -> None:
        """Validate that .agent/config.json exists and parses as valid JSON."""
        config_path = os.path.join(self.parent_dir, ".agent", "config.json")
        self.assertTrue(os.path.isfile(config_path), f"config.json not found at {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                self.fail(f"config.json is not valid JSON: {e}")

        # Check for required fields
        self.assertIn("agent_name", config)
        self.assertIn("models", config)
        self.assertIn("timeout_seconds", config)
        self.assertIn("max_retries", config)

    def test_database_client(self) -> None:
        """Validate that the database client can be initialized and queried."""
        self.assertIsNotNone(DatabaseClient, "DatabaseClient could not be imported.")
        
        # Initialize isolated database client
        db = DatabaseClient(db_path=self.sqlite_db_path)
        
        # Test memory table insert and query
        db.save_memory("test_key", "test_value", "test_category")
        val = db.get_memory("test_key")
        self.assertEqual(val, "test_value")
        db.close()

    def test_database_client_new_tables_and_queries(self) -> None:
        """Test newly added table queries (sessions, handoffs, open issues, latest activity)."""
        self.assertIsNotNone(DatabaseClient, "DatabaseClient could not be imported.")
        
        db = DatabaseClient(db_path=self.sqlite_db_path)
        
        # Initially, there shouldn't be any active/latest activity or open issues
        latest = db.get_latest_activity()
        self.assertIsNone(latest)
        
        open_issues = db.get_open_issues()
        self.assertEqual(len(open_issues), 0)
        
        # 1. Log open and closed issues
        db.log_issue("gh-1", "Open Issue", "feature", "open", None)
        db.log_issue("gh-2", "Closed Issue", "bug", "closed", None)
        
        open_issues = db.get_open_issues()
        self.assertEqual(len(open_issues), 1)
        self.assertEqual(open_issues[0]["github_id"], "gh-1")
        self.assertEqual(open_issues[0]["title"], "Open Issue")
        
        # 2. Save session and check latest activity
        db.save_session("session-abc", "dev_agent", "Implement features", [])
        latest = db.get_latest_activity()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["type"], "session")
        self.assertEqual(latest["agent"], "dev_agent")
        self.assertEqual(latest["task"], "Implement features")
        self.assertEqual(latest["status"], "active")
        
        # 3. Log a handoff with newer activity and check latest activity
        import time
        time.sleep(1)  # Ensure a different timestamp if database resolution is low
        db.log_handoff("dev_agent", "qa_agent", "plan", "/path/to/contract.md", "pending")
        
        latest = db.get_latest_activity()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["type"], "handoff")
        self.assertEqual(latest["agent"], "dev_agent -> qa_agent")
        self.assertEqual(latest["task"], "plan")
        self.assertEqual(latest["status"], "pending")
        
        db.close()

    def test_main_cli_parsing(self) -> None:
        """Test parser arguments and basic entry points of main.py."""
        # Test default/help output or incorrect command exit code
        with patch("sys.argv", ["main.py"]):
            with self.assertRaises(SystemExit) as cm:
                main.main()
            self.assertEqual(cm.exception.code, 1)

        # Test valid parsing for db-init, mock handle_db_init to prevent actual creation
        with patch("sys.argv", ["main.py", "db-init"]), \
             patch("main.handle_db_init") as mock_db_init:
            main.main()
            mock_db_init.assert_called_once()

    def test_main_interactive_loop(self) -> None:
        """Test the interactive run loop with simulated user inputs."""
        inputs = ["gh-1", "yes", "exit"]
        input_mock = lambda *args: inputs.pop(0)

        # Pre-seed the test database with open issues and a session/handoff
        db = DatabaseClient(db_path=self.sqlite_db_path)
        db.log_issue("gh-1", "Task 1", "feature", "open", None)
        db.close()

        # Mock database initialization to use our test db path
        with patch("builtins.input", side_effect=input_mock), \
             patch("tools.database_client.DatabaseClient") as mock_db_class:
            
            # Create instance pointing to our test db
            test_db = DatabaseClient(db_path=self.sqlite_db_path)
            mock_db_class.return_value = test_db
            
            # Execute interactive run loop inside main.py
            with patch("sys.argv", ["main.py", "run"]):
                with self.assertRaises(SystemExit) as cm:
                    main.main()
                self.assertEqual(cm.exception.code, 0)
            
            # Confirm database states updated
            issue = test_db.get_issue("gh-1")
            self.assertIsNotNone(issue)
            self.assertEqual(issue["status"], "closed")
            
            test_db.close()


if __name__ == "__main__":
    unittest.main()
