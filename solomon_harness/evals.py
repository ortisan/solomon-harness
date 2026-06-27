"""Shared agent evaluation suite.

build_agent_suite(harness_dir) returns a unittest.TestSuite that validates the
agent rooted at harness_dir (its persona and config) and exercises the shared
harness loop and memory client. Every agent runs the same suite against its own
directory through `python main.py eval`, so the checks live in one place.
"""

import json
import os
import tempfile
import unicodedata
import unittest
from typing import Any, Optional, Tuple
from unittest.mock import patch

from solomon_harness import cli
from solomon_harness.tools.database_client import DatabaseClient

CLICHES = [
    "delve",
    "leverage",
    "testament",
    "dive into",
    "feel free",
    "in summary",
    "moreover",
    "firstly",
    "secondly",
    "lastly",
]


def _has_emoji(text: str) -> Tuple[bool, Optional[str]]:
    for char in text:
        cp = ord(char)
        is_emoji = (
            (0x1F000 <= cp <= 0x1FFFF)
            or (0x2600 <= cp <= 0x27BF)
            or (0x2300 <= cp <= 0x23FF)
        )
        if not is_emoji:
            try:
                cat = unicodedata.category(char)
                if cat == "So":
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


def build_agent_suite(harness_dir: str) -> unittest.TestSuite:
    """Builds the shared evaluation suite parameterized by an agent directory."""

    class TestAgentEvals(unittest.TestCase):
        """Verifies an agent's files, configuration and the shared runner loop."""

        def setUp(self) -> None:
            self.parent_dir = harness_dir
            # Isolate the DB so tests do not write to the project memory store.
            self.temp_dir = tempfile.TemporaryDirectory()
            self.sqlite_db_path = os.path.join(self.temp_dir.name, "harness_test.db")

        def tearDown(self) -> None:
            self.temp_dir.cleanup()

        def test_persona_markdown(self) -> None:
            """Validate that persona.md has no emojis or AI cliches."""
            persona_path = os.path.join(self.parent_dir, "persona.md")
            self.assertTrue(
                os.path.isfile(persona_path), f"persona.md not found at {persona_path}"
            )

            with open(persona_path, "r", encoding="utf-8") as f:
                content = f.read()

            emoji_found, emoji_char = _has_emoji(content)
            self.assertFalse(
                emoji_found, f"Emoji or icon '{emoji_char}' found in persona.md."
            )

            content_lower = content.lower()
            for cliche in CLICHES:
                self.assertNotIn(
                    cliche, content_lower, f"AI cliche '{cliche}' found in persona.md."
                )

        def test_config_json(self) -> None:
            """Validate that .agent/config.json exists and parses as valid JSON."""
            config_path = os.path.join(self.parent_dir, ".agent", "config.json")
            self.assertTrue(
                os.path.isfile(config_path), f"config.json not found at {config_path}"
            )

            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError as e:
                    self.fail(f"config.json is not valid JSON: {e}")

            self.assertIn("agent_name", config)
            self.assertIn("models", config)
            self.assertIn("timeout_seconds", config)
            self.assertIn("max_retries", config)

        def test_database_client(self) -> None:
            """Validate that the database client can be initialized and queried."""
            db = DatabaseClient(db_path=self.sqlite_db_path)
            db.save_memory("test_key", "test_value", "test_category")
            val = db.get_memory("test_key")
            self.assertEqual(val, "test_value")
            db.close()

        def test_database_client_new_tables_and_queries(self) -> None:
            """Test sessions, handoffs, open issues and latest activity queries."""
            db = DatabaseClient(db_path=self.sqlite_db_path)

            latest = db.get_latest_activity()
            self.assertIsNone(latest)

            open_issues = db.get_open_issues()
            self.assertEqual(len(open_issues), 0)

            db.log_issue("gh-1", "Open Issue", "feature", "open", None)
            db.log_issue("gh-2", "Closed Issue", "bug", "closed", None)

            open_issues = db.get_open_issues()
            self.assertEqual(len(open_issues), 1)
            self.assertEqual(open_issues[0]["github_id"], "gh-1")
            self.assertEqual(open_issues[0]["title"], "Open Issue")

            db.save_session("session-abc", "dev_agent", "Implement features", [])
            latest = db.get_latest_activity()
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["type"], "session")
            self.assertEqual(latest["agent"], "dev_agent")
            self.assertEqual(latest["task"], "Implement features")
            self.assertEqual(latest["status"], "active")

            import time

            time.sleep(1)  # Ensure a different timestamp if database resolution is low
            db.log_handoff(
                "dev_agent", "qa_agent", "plan", "/path/to/contract.md", "pending"
            )

            latest = db.get_latest_activity()
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["type"], "handoff")
            self.assertEqual(latest["agent"], "dev_agent -> qa_agent")
            self.assertEqual(latest["task"], "plan")
            self.assertEqual(latest["status"], "pending")

            db.close()

        def test_main_cli_parsing(self) -> None:
            """Test parser arguments and basic entry points of the CLI."""
            with self.assertRaises(SystemExit) as cm:
                cli.main(harness_dir=harness_dir, argv=[])
            self.assertEqual(cm.exception.code, 1)

            with patch("solomon_harness.cli.handle_db_init") as mock_db_init:
                cli.main(harness_dir=harness_dir, argv=["db-init"])
                mock_db_init.assert_called_once()

        def test_main_interactive_loop(self) -> None:
            """Test the interactive run loop with simulated user inputs."""
            inputs = ["gh-1", "yes", "exit"]

            def input_mock(*args: Any) -> str:
                return inputs.pop(0)

            db = DatabaseClient(db_path=self.sqlite_db_path)
            db.log_issue("gh-1", "Task 1", "feature", "open", None)
            db.close()

            with (
                patch("builtins.input", side_effect=input_mock),
                patch(
                    "solomon_harness.tools.database_client.DatabaseClient"
                ) as mock_db_class,
            ):
                test_db = DatabaseClient(db_path=self.sqlite_db_path)
                mock_db_class.return_value = test_db

                with self.assertRaises(SystemExit) as cm:
                    cli.main(harness_dir=harness_dir, argv=["run"])
                self.assertEqual(cm.exception.code, 0)

                issue = test_db.get_issue("gh-1")
                self.assertIsNotNone(issue)
                assert issue is not None
                self.assertEqual(issue["status"], "closed")

                test_db.close()

    loader = unittest.TestLoader()
    return loader.loadTestsFromTestCase(TestAgentEvals)
