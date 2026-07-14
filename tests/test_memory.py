import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

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


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self, n=None):
        return self._body[:n] if n else self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestIsServing(unittest.TestCase):
    def test_true_for_surreal_version_banner(self):
        with patch("urllib.request.urlopen", return_value=_Resp(200, "surrealdb-2.1.0")):
            self.assertTrue(memory.is_serving("localhost", 8000))

    def test_false_for_foreign_service(self):
        # A non-SurrealDB process that answers /version with something else.
        with patch("urllib.request.urlopen", return_value=_Resp(200, "nginx/1.25")):
            self.assertFalse(memory.is_serving("localhost", 8000))

    def test_false_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            self.assertFalse(memory.is_serving("localhost", 8000))


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

    def test_already_running_when_surreal_serving(self):
        called = []

        def fake_run(cmd, **kwargs):
            called.append(cmd)
            return _Proc(0)

        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=True), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["ok"])
        self.assertTrue(res["already_running"])
        self.assertEqual(called, [])

    def test_serving_backend_with_stale_compose_is_recreated(self):
        # A backend already serving on an all-interfaces bind is the very
        # exposure the loopback pin closes: memory-up must recreate it now,
        # not skip it as already_running (PR #245 review blocker).
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _Proc(0, "", "")

        with patch.object(memory, "heal_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "is_serving", return_value=True), \
             patch.object(memory, "ensure_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.ensure_memory_up(self.root, wait_seconds=5)
        self.assertTrue(res["ok"])
        self.assertTrue(res["started"])
        self.assertTrue(res["loopback_healed"])
        self.assertTrue(any("up" in c and "-d" in c for c in calls))

    def test_port_conflict_when_foreign_process_holds_port(self):
        called = []

        def fake_run(cmd, **kwargs):
            called.append(cmd)
            return _Proc(0)

        # Not SurrealDB (is_serving False) but the port is open (_tcp_open True):
        # a foreign process holds it. We must not run compose.
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=False), \
             patch.object(memory, "_tcp_open", return_value=True), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.ensure_memory_up(self.root)
        self.assertFalse(res["ok"])
        self.assertTrue(res["port_conflict"])
        self.assertEqual(called, [])

    def test_missing_compose_file(self):
        # No shared compose and none bundled -> reported, not started.
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=False), \
             patch.object(memory, "_tcp_open", return_value=False), \
             patch.object(memory, "ensure_home_compose", return_value=None):
            res = memory.ensure_memory_up(self.root)
        self.assertFalse(res["ok"])
        self.assertIn("shared docker-compose.yml not found", res["error"])

    def test_docker_unavailable(self):
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=False), \
             patch.object(memory, "_tcp_open", return_value=False), \
             patch.object(memory, "ensure_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "_compose_command", return_value=None):
            res = memory.ensure_memory_up(self.root)
        self.assertFalse(res["ok"])
        self.assertIn("Docker is unavailable", res["error"])

    def test_starts_compose_from_shared_home_then_serving(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _Proc(0, "", "")

        # Port free (_tcp_open False). is_serving: False on the pre-check, True
        # after `up -d`. Compose comes from the shared home, not the project.
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", side_effect=[False, True]), \
             patch.object(memory, "_tcp_open", return_value=False), \
             patch.object(memory, "ensure_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", side_effect=fake_run):
            res = memory.ensure_memory_up(self.root, wait_seconds=5)
        self.assertTrue(res["ok"])
        self.assertTrue(res["started"])
        self.assertIn("/home/sh/docker-compose.yml", calls[0])
        self.assertIn("up", calls[0])
        self.assertIn("-d", calls[0])

    def test_compose_failure_is_reported(self):
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=False), \
             patch.object(memory, "_tcp_open", return_value=False), \
             patch.object(memory, "ensure_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            res = memory.ensure_memory_up(self.root, wait_seconds=1)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "boom")


class TestMemoryUpReconcile(unittest.TestCase):
    """ADR-0002 promises auto-reconcile at memory-up / SessionStart, not only via
    the manual `memory sync`. ensure_memory_up must replay pending mirror records
    once the backend is confirmed up, and must never let that step break the hook."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".agent"))
        with open(os.path.join(self.root, ".agent", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"database": {"provider": "surrealdb", "url": "ws://localhost:8000/rpc"}}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconcile_runs_when_backend_already_up(self):
        recon = MagicMock(return_value={"synced": 1, "remaining": 0})
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=True), \
             patch.object(memory, "reconcile_pending", recon):
            res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["already_running"])
        recon.assert_called_once_with(self.root)

    def test_reconcile_runs_after_compose_start(self):
        recon = MagicMock(return_value={"synced": 0, "remaining": 0})
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", side_effect=[False, True]), \
             patch.object(memory, "_tcp_open", return_value=False), \
             patch.object(memory, "ensure_home_compose", return_value="/home/sh/docker-compose.yml"), \
             patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
             patch.object(memory, "reconcile_pending", recon), \
             patch("subprocess.run", return_value=_Proc(0, "", "")):
            res = memory.ensure_memory_up(self.root, wait_seconds=5)
        self.assertTrue(res["started"])
        recon.assert_called_once_with(self.root)

    def test_memory_up_never_raises_when_reconcile_blows_up(self):
        # Drive the real guard: a pending record forces a client build, and the
        # build raises. ensure_memory_up must still return cleanly -- the
        # session-start hook is never broken (best-effort, swallowing).
        import solomon_harness.tools.database_client as dbc
        with patch.object(memory, "heal_home_compose", return_value=None), \
             patch.object(memory, "is_serving", return_value=True), \
             patch("solomon_harness.healthcheck.pending_reconcile_count", return_value=1), \
             patch.object(dbc, "DatabaseClient", side_effect=RuntimeError("boom")):
            with redirect_stderr(io.StringIO()):
                res = memory.ensure_memory_up(self.root)
        self.assertTrue(res["already_running"])

    def test_reconcile_pending_skips_client_when_nothing_pending(self):
        # The common case: nothing pending, so no client is built and no socket is
        # opened. If a client were built the patched factory would record the call.
        import solomon_harness.tools.database_client as dbc
        built = MagicMock(side_effect=AssertionError("must not build a client"))
        with patch("solomon_harness.healthcheck.pending_reconcile_count", return_value=0), \
             patch.object(dbc, "DatabaseClient", built):
            result = memory.reconcile_pending(self.root)
        self.assertEqual(result, {"synced": 0, "remaining": 0})


class TestEnsureHomeCompose(unittest.TestCase):
    def test_copies_packaged_compose_into_empty_home(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as pkg:
            src = os.path.join(pkg, "docker-compose.yml")
            with open(src, "w", encoding="utf-8") as f:
                f.write("services: {}\n")
            with patch.object(memory, "harness_home", return_value=home), \
                 patch.object(memory, "_packaged_compose", return_value=src):
                dest = memory.ensure_home_compose()
            self.assertEqual(dest, os.path.join(home, "docker-compose.yml"))
            self.assertTrue(os.path.isfile(dest))

    def test_returns_existing_without_recopy(self):
        with tempfile.TemporaryDirectory() as home:
            existing = os.path.join(home, "docker-compose.yml")
            with open(existing, "w", encoding="utf-8") as f:
                f.write("services: {existing: true}\n")
            with patch.object(memory, "harness_home", return_value=home), \
                 patch.object(memory, "_packaged_compose", return_value=None):
                dest = memory.ensure_home_compose()
            self.assertEqual(dest, existing)

    def test_templates_assigned_host_port(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as pkg:
            src = os.path.join(pkg, "docker-compose.yml")
            with open(src, "w", encoding="utf-8") as f:
                f.write('    ports:\n      - "127.0.0.1:8099:8000"\n')
            with patch.object(memory, "harness_home", return_value=home), \
                 patch.object(memory, "_packaged_compose", return_value=src), \
                 patch.object(memory, "assigned_memory_port", return_value=8137):
                dest = memory.ensure_home_compose()
            with open(dest, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"127.0.0.1:8137:8000"', content)
            self.assertNotIn('"127.0.0.1:8099:8000"', content)

    def test_bare_port_mapping_is_pinned_to_loopback(self):
        # A pre-loopback home compose (bare "<port>:8000") must come out bound to
        # 127.0.0.1: the store ships a fixed root/root development credential, so
        # the published mapping must never listen on all interfaces.
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as pkg:
            src = os.path.join(pkg, "docker-compose.yml")
            with open(src, "w", encoding="utf-8") as f:
                f.write('    ports:\n      - "8000:8000"\n')
            with patch.object(memory, "harness_home", return_value=home), \
                 patch.object(memory, "_packaged_compose", return_value=src), \
                 patch.object(memory, "assigned_memory_port", return_value=8137):
                dest = memory.ensure_home_compose()
            with open(dest, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"127.0.0.1:8137:8000"', content)
            self.assertNotIn('"8000:8000"', content)

    def test_existing_home_compose_is_healed(self):
        # ensure_home_compose used to early-return an existing file untouched,
        # leaving pre-loopback installs exposed forever (PR #245 review
        # blocker). An existing stale file must come back pinned, with the
        # machine's already-assigned port preserved.
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, "docker-compose.yml")
            with open(dest, "w", encoding="utf-8") as f:
                f.write('    ports:\n      - "8137:8000"\n      - "3000:80"\n')
            with patch.object(memory, "harness_home", return_value=home):
                out = memory.ensure_home_compose()
            self.assertEqual(out, dest)
            with open(dest, encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"127.0.0.1:8137:8000"', content)
            self.assertIn('"127.0.0.1:3000:80"', content)


class TestPinPublishedToLoopback(unittest.TestCase):
    def test_pins_bare_and_zero_bind_preserving_ports(self):
        text = '    ports:\n      - "8099:8000"\n      - "0.0.0.0:3000:80"\n'
        pinned = memory._pin_published_to_loopback(text)
        self.assertIn('"127.0.0.1:8099:8000"', pinned)
        self.assertIn('"127.0.0.1:3000:80"', pinned)

    def test_idempotent_on_already_pinned_text(self):
        text = '    ports:\n      - "127.0.0.1:8137:8000"\n      - "127.0.0.1:3000:80"\n'
        self.assertEqual(memory._pin_published_to_loopback(text), text)

    def test_leaves_unrelated_mappings_and_healthcheck_alone(self):
        text = (
            '      - "5432:5432"\n'
            '      test: ["CMD", "/surreal", "isready", "--endpoint", "http://localhost:8000"]\n'
        )
        self.assertEqual(memory._pin_published_to_loopback(text), text)


class TestHealHomeCompose(unittest.TestCase):
    def test_pins_existing_stale_file_preserving_port(self):
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, "docker-compose.yml")
            with open(dest, "w", encoding="utf-8") as f:
                f.write('    ports:\n      - "8137:8000"\n      - "3000:80"\n')
            with patch.object(memory, "harness_home", return_value=home):
                healed = memory.heal_home_compose()
            self.assertEqual(healed, dest)
            with open(dest, encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"127.0.0.1:8137:8000"', content)
            self.assertIn('"127.0.0.1:3000:80"', content)

    def test_returns_none_when_already_pinned(self):
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, "docker-compose.yml")
            text = '    ports:\n      - "127.0.0.1:8137:8000"\n'
            with open(dest, "w", encoding="utf-8") as f:
                f.write(text)
            with patch.object(memory, "harness_home", return_value=home):
                self.assertIsNone(memory.heal_home_compose())
            with open(dest, encoding="utf-8") as f:
                self.assertEqual(f.read(), text)

    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(memory, "harness_home", return_value=home):
                self.assertIsNone(memory.heal_home_compose())


class TestStopMemory(unittest.TestCase):
    def test_missing_compose_file(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(memory, "harness_home", return_value=home):
                res = memory.stop_memory()
        self.assertFalse(res["ok"])

    def test_runs_down_from_shared_home(self):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return _Proc(0)

        with tempfile.TemporaryDirectory() as home:
            with open(os.path.join(home, "docker-compose.yml"), "w", encoding="utf-8") as f:
                f.write("services: {}\n")
            with patch.object(memory, "harness_home", return_value=home), \
                 patch.object(memory, "_compose_command", return_value=["docker", "compose"]), \
                 patch("subprocess.run", side_effect=fake_run):
                res = memory.stop_memory()
        self.assertTrue(res["ok"])
        self.assertIn("down", captured[0])


if __name__ == "__main__":
    unittest.main()
