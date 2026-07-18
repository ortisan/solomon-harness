import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from solomon_harness import home, memory
from solomon_harness.tools.database_client import DatabaseClient

_COMPOSE = (
    "services:\n"
    "  surrealdb:\n"
    "    command: start --username root --password root --log info rocksdb:/data/solomon.db\n"
    '    ports:\n      - "127.0.0.1:8099:8000"\n'
)


class TestCredentialFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SOLOMON_HARNESS_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_password_generated_persisted_0600_and_idempotent(self):
        first = home.assigned_memory_password()
        self.assertNotEqual(first, "root")
        self.assertGreaterEqual(len(first), 16)
        path = os.path.join(self.tmp.name, "credentials.json")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(home.assigned_memory_password(), first)
        self.assertEqual(home.generated_memory_password(), first)

    def test_generated_returns_none_when_absent(self):
        self.assertIsNone(home.generated_memory_password())


class TestComposeTemplating(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SOLOMON_HARNESS_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_set_password_replaces_value(self):
        out = memory._set_password(_COMPOSE, "SECRET-abc_123")
        self.assertIn("--password SECRET-abc_123 ", out)
        self.assertNotIn("--password root", out)

    def test_heal_rotates_literal_root_password(self):
        dest = os.path.join(self.tmp.name, "docker-compose.yml")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_COMPOSE)
        self.assertEqual(memory.heal_home_compose(), dest)
        content = open(dest, encoding="utf-8").read()
        self.assertNotIn("--password root", content)
        self.assertIn(f"--password {home.generated_memory_password()}", content)

    def test_heal_is_noop_once_rotated(self):
        dest = os.path.join(self.tmp.name, "docker-compose.yml")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_COMPOSE)
        memory.heal_home_compose()
        self.assertIsNone(memory.heal_home_compose())

    def test_ensure_home_compose_templates_a_non_root_password(self):
        src = os.path.join(self.tmp.name, "src-compose.yml")
        with open(src, "w", encoding="utf-8") as f:
            f.write(_COMPOSE)
        with patch("solomon_harness.memory._packaged_compose", return_value=src):
            dest = memory.ensure_home_compose()
        content = open(dest, encoding="utf-8").read()
        self.assertNotIn("--password root", content)
        self.assertIn(f"--password {home.generated_memory_password()}", content)


class TestClientReadsGeneratedCredential(unittest.TestCase):
    def test_local_client_uses_generated_password_not_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agent"))
            with open(os.path.join(tmp, ".agent", "config.json"), "w", encoding="utf-8") as f:
                f.write('{"database": {"provider": "surrealdb", "url": "ws://localhost:8099/rpc"}}')
            with patch.dict(os.environ, {"SOLOMON_HARNESS_HOME": tmp}):
                generated = home.assigned_memory_password()
                fake = types.ModuleType("surrealdb")
                fake.Surreal = MagicMock()
                with patch.dict(sys.modules, {"surrealdb": fake}), patch.object(
                    DatabaseClient, "_connect_surreal", return_value=True
                ), patch.object(
                    DatabaseClient, "_bootstrap_surreal_schema", return_value=None
                ), patch.object(DatabaseClient, "_init_spectron", return_value=None):
                    client = DatabaseClient(harness_dir=tmp)
                self.assertEqual(client._surreal_password, generated)
                self.assertNotEqual(client._surreal_password, "root")


if __name__ == "__main__":
    unittest.main()
