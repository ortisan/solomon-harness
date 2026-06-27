import unittest
import os
import sys
import json
import unicodedata

# Dynamically locate the parent agent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import DatabaseClient from tools
try:
    from tools.database_client import DatabaseClient
except ImportError:
    DatabaseClient = None


class TestAgentEvals(unittest.TestCase):
    """Unit tests for verifying agent files and configurations."""

    def setUp(self):
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

    def _has_emoji(self, text):
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

    def test_persona_markdown(self):
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

    def test_config_json(self):
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

    def test_database_client(self):
        """Validate that the database client can be initialized and queried."""
        self.assertIsNotNone(DatabaseClient, "DatabaseClient could not be imported.")
        
        # Initialize database client, it should dynamically connect to memory/long_term/harness.db
        db = DatabaseClient()
        
        # Test memory table insert and query
        db.save_memory("test_key", "test_value", "test_category")
        val = db.get_memory("test_key")
        self.assertEqual(val, "test_value")


if __name__ == "__main__":
    unittest.main()
