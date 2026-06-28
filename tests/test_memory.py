import json
import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import memory


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestHostPort(unittest.TestCase):
    def test_parses_ws_url(self):
        self.assertEqual(memory._host_port("ws://localhost:8000/rpc"), ("localhost", 8000))

    def test_parses_without_port(self):
        self.assertEqual(memory._host_port("ws://example.com/rpc"), ("example.com", 8000))

    def test_parses_ip_and_port(self):
        self.assertEqual(memory._host_port("ws://127.0.0.1:9000/rpc"), ("127.0.0.1", 9000))


class TestReadDbUrl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".agent"))

    def tearDown(self):
        self.tmp.cleanup()

    def _write_config(self, db):
        with open(os.path.join(self.root, ".agent", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"database": db}, f)

    def test_reads_provider_and_url(self):
        self._write_config({"provider": "surrealdb", "url": "ws://localhost:8000/rpc"})
        provider, url = memory._read_db_url(self.root)
        self.assertEqual(provider, "surrealdb")
        self.assertEqual(url, "ws://localhost:8000/rpc")

    def test_defaults_when_no_config(self):
        provider, url = memory._read_db_url(self.root)
        self.assertEqual(provider, "surrealdb")
        self.assertEqual(url, memory.DEFAULT_URL)


class TestEnsureMemoryUp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".agent"))
        self._config({"provider": "surrealdb", "url": "ws://localhost:8000/rpc"})

    def tearDown(self):
        self.tmp.cleanup()

    def _config(self, db):
        with open(os.path.join(self.root, ".agent", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"database": db}, f)

    def _compose_file(self):
        with open(os.path.join(self.root, "docker-compose.yml"), "w", encoding="utf-8") as f:
            f.write("services: {}\n")

    def test_skips_non_surrealdb(self):
        self._config({"provider": "sqlite"})
        res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["ok"])
        self.assertIn("skipped", res)

    def test_skips_remote_host(self):
        self._config({"provider": "surrealdb", "url": "ws://db.prod.example:8000/rpc"})
        res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["ok"])
        self.assertIn("not local", res["skipped"])

    def test_already_running_when_reachable(self):
        with patch.object(memory, "is_reachable", return_value=True):
            res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["ok"])
        self.assertTrue(res["already_running"])

    def test_missing_compose_file(self):
        with patch.object(memory, "is_reachable", return_value=False):
            res = memory.ensure_memory_up(self.root)
        self.assertFalse(res["ok"])
        self.assertIn("docker-compose.yml not found", res["error"])

    def test_docker_unavailable(self):
        self._compose_file()
        with patch.object(memory, "is_reachable", return_value=False), \
             patch.object(memory, "_compose_command", return_value=None):
            res = memory.ensure_memory_up(self.root)
        self.assertFalse(res["ok"])
        self.assertIn("Docker is unavailable", res["error"])

    def test_starts_compose_then_reachable(self):
        self._compose_file()
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _Proc(0, "", "")

        # First is_reachable (pre-check) is False; after `up -d` it becomes True.
        with patch.object(memory, "is_reachable", side_effect=[False, True]), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.ensure_memory_up(self.root, wait_seconds=5)
        self.assertTrue(res["ok"])
        self.assertTrue(res["started"])
        self.assertIn("up", calls[0])
        self.assertIn("-d", calls[0])

    def test_compose_failure_is_reported(self):
        self._compose_file()
        with patch.object(memory, "is_reachable", return_value=False), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            res = memory.ensure_memory_up(self.root, wait_seconds=1)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "boom")


class TestStopMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_compose_file(self):
        res = memory.stop_memory(self.root)
        self.assertFalse(res["ok"])

    def test_runs_down(self):
        with open(os.path.join(self.root, "docker-compose.yml"), "w", encoding="utf-8") as f:
            f.write("services: {}\n")
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return _Proc(0)

        with patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.stop_memory(self.root)
        self.assertTrue(res["ok"])
        self.assertIn("down", captured[0])


if __name__ == "__main__":
    unittest.main()
