import json
import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import healthcheck as hc


class _P:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestDocker(unittest.TestCase):
    def test_not_installed(self):
        with patch.object(hc.shutil, "which", return_value=None):
            c = hc.check_docker()
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("not installed", c["detail"])

    def test_daemon_down(self):
        with patch.object(hc.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(hc, "_run", return_value=_P(1)):
            c = hc.check_docker()
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("not running", c["detail"])
        self.assertIn("Start Docker", c["fix"])

    def test_running(self):
        with patch.object(hc.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(hc, "_run", return_value=_P(0)):
            c = hc.check_docker()
        self.assertEqual(c["status"], hc.OK)


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".agent"))
        with open(os.path.join(self.root, ".agent", "config.json"), "w") as f:
            json.dump({"database": {"provider": "surrealdb", "url": "ws://localhost:8099/rpc", "database": "harness"}}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_serving(self):
        with patch.object(hc.memory, "is_serving", return_value=True), \
             patch.object(hc, "derive_tenant", return_value="acme-widget"):
            c = hc.check_memory(self.root)
        self.assertEqual(c["status"], hc.OK)
        self.assertIn("acme-widget", c["detail"])

    def test_port_conflict(self):
        with patch.object(hc.memory, "is_serving", return_value=False), \
             patch.object(hc.memory, "_tcp_open", return_value=True), \
             patch.object(hc, "derive_tenant", return_value="acme-widget"):
            c = hc.check_memory(self.root)
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("held by a non-SurrealDB", c["detail"])

    def test_not_running_sqlite_fallback(self):
        with patch.object(hc.memory, "is_serving", return_value=False), \
             patch.object(hc.memory, "_tcp_open", return_value=False), \
             patch.object(hc, "derive_tenant", return_value="acme-widget"):
            c = hc.check_memory(self.root)
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("SQLite fallback", c["detail"])


class TestGitHub(unittest.TestCase):
    def test_missing_project_scope(self):
        with patch.object(hc.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(hc, "_run", return_value=_P(0, "Token scopes: 'repo', 'read:org'")):
            c = hc.check_github()
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("project", c["fix"])

    def test_has_project_scope(self):
        with patch.object(hc.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(hc, "_run", return_value=_P(0, "Token scopes: 'repo', 'project', 'read:project'")):
            c = hc.check_github()
        self.assertEqual(c["status"], hc.OK)

    def test_not_authenticated(self):
        with patch.object(hc.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(hc, "_run", return_value=_P(1, "", "not logged in")):
            c = hc.check_github()
        self.assertEqual(c["status"], hc.WARN)


class TestGlobalInstall(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            c = hc.check_global_install(claude_dir=d)
        self.assertEqual(c["status"], hc.WARN)

    def test_present(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "agents"))
            os.makedirs(os.path.join(d, "commands"))
            with open(os.path.join(d, "agents", "qa.md"), "w") as f:
                f.write("x")
            with open(os.path.join(d, "commands", "solomon-workflow.md"), "w") as f:
                f.write("x")
            c = hc.check_global_install(claude_dir=d)
        self.assertEqual(c["status"], hc.OK)


class TestSharedHome(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            c = hc.check_shared_home(home=os.path.join(d, "nope"))
        self.assertEqual(c["status"], hc.WARN)

    def test_present(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "docker-compose.yml"), "w") as f:
                f.write("services: {}")
            c = hc.check_shared_home(home=d)
        self.assertEqual(c["status"], hc.OK)


class TestReport(unittest.TestCase):
    def test_format_and_pending(self):
        checks = [
            hc._check("A", hc.OK, "fine"),
            hc._check("B", hc.WARN, "degraded", "do X"),
        ]
        report = hc.format_report(checks)
        self.assertIn("A: fine", report)
        self.assertIn("-> do X", report)
        pending = hc.pending_summary(checks)
        self.assertEqual(pending, ["B: do X"])

    def test_run_checks_never_raises_and_returns_all(self):
        with patch.object(hc, "check_docker", side_effect=RuntimeError("boom")):
            checks = hc.run_checks("/tmp")
        # The failing check is captured as a warn rather than propagating.
        self.assertTrue(any(c["status"] == hc.WARN for c in checks))
        self.assertEqual(len(checks), 10)


class TestHostAdapters(unittest.TestCase):
    def _matrix(self):
        capabilities = {
            "headless",
            "instructions",
            "mcp",
            "pre_tool_guard",
            "session_start",
            "specialists",
            "workflows",
        }
        active = {name: "active" for name in capabilities}
        configured = dict(active, mcp="configured", pre_tool_guard="configured",
                          session_start="configured")
        pending = dict(configured, mcp="pending_trust",
                       pre_tool_guard="pending_trust", session_start="pending_trust")
        return {
            "agy": {"status": "configured", "capabilities": capabilities,
                    "capability_states": configured},
            "claude": {"status": "configured", "capabilities": capabilities,
                       "capability_states": configured},
            "codex": {"status": "pending_trust", "capabilities": capabilities,
                      "capability_states": pending},
        }

    def test_reports_each_host_and_codex_pending_trust(self):
        with patch.object(hc, "inspect_capabilities", return_value=self._matrix()):
            checks = hc.check_host_adapters("/repo")

        self.assertEqual([item["name"] for item in checks], [
            "AGY adapter", "Claude adapter", "Codex adapter",
        ])
        self.assertEqual(checks[0]["status"], hc.OK)
        self.assertEqual(checks[1]["status"], hc.OK)
        self.assertEqual(checks[2]["status"], hc.WARN)
        self.assertIn("project trust", checks[2]["detail"])
        self.assertIn("approve", checks[2]["fix"])

    def test_reports_missing_capabilities_without_raising(self):
        matrix = self._matrix()
        matrix["claude"]["capabilities"] = {"headless", "instructions"}
        matrix["claude"]["capability_states"] = {
            "headless": "active",
            "instructions": "active",
            "mcp": "unavailable",
            "pre_tool_guard": "unavailable",
            "session_start": "unavailable",
            "specialists": "unavailable",
            "workflows": "unavailable",
        }
        matrix["claude"]["status"] = "active"

        with patch.object(hc, "inspect_capabilities", return_value=matrix):
            check = hc.check_host_adapters("/repo")[1]

        self.assertEqual(check["status"], hc.WARN)
        self.assertIn("mcp", check["detail"])
        self.assertIn("compile", check["fix"])


class TestPendingReconcile(unittest.TestCase):
    def _write_mirror(self, root, kind, name, synced):
        directory = os.path.join(root, ".solomon", "memory-mirror", kind)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(
                f"---\nid: {name}\nkind: {kind}\n"
                f"created_at: 2026-06-28T22:00:00+00:00\nsynced: {synced}\n---\n\n"
                f"# {kind} record\n"
            )

    def test_counts_only_unsynced_mirror_files(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_mirror(d, "release", "r0", "false")
            self._write_mirror(d, "release", "r1", "true")
            self._write_mirror(d, "decision", "d0", "false")
            self.assertEqual(hc.pending_reconcile_count(d), 2)
            c = hc.check_pending_reconcile(d)
            self.assertEqual(c["status"], hc.WARN)
            self.assertIn("2", c["detail"])
            self.assertIn("memory sync", c["fix"])

    def test_zero_pending_when_no_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hc.pending_reconcile_count(d), 0)
            self.assertEqual(hc.check_pending_reconcile(d)["status"], hc.OK)

    def test_honors_harness_mirror_root_env(self):
        # The mirror can be redirected with HARNESS_MIRROR_ROOT (the same precedence
        # the client uses). The healthcheck must read pending records from there,
        # not from a hard-coded <workspace>/.solomon/memory-mirror, or it would
        # report 0 pending while records sit elsewhere.
        with tempfile.TemporaryDirectory() as workspace, \
             tempfile.TemporaryDirectory() as mirror_root:
            directory = os.path.join(mirror_root, "release")
            os.makedirs(directory)
            with open(os.path.join(directory, "r0.md"), "w", encoding="utf-8") as f:
                f.write(
                    "---\nid: r0\nkind: release\n"
                    "created_at: 2026-06-28T22:00:00+00:00\nsynced: false\n---\n\n"
                    "# release record\n"
                )
            # The default location under the workspace is empty.
            with patch.dict(os.environ, {"HARNESS_MIRROR_ROOT": mirror_root}):
                self.assertEqual(hc.pending_reconcile_count(workspace), 1)

    def test_run_checks_includes_pending_reconcile(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_mirror(d, "release", "r0", "false")
            checks = hc.run_checks(d)
        reconcile = [c for c in checks if c["name"] == "Memory reconcile"]
        self.assertEqual(len(reconcile), 1)
        self.assertEqual(reconcile[0]["status"], hc.WARN)
        self.assertIn("1", reconcile[0]["detail"])


class TestGitConfigCheck(unittest.TestCase):
    def test_clean_config(self):
        with patch.object(hc.subprocess, "run", side_effect=[_P(1), _P(0, "false")]):
            c = hc.check_git_config("/tmp")
        self.assertEqual(c["status"], hc.OK)
        self.assertIn("clean", c["detail"])

    def test_stray_worktree(self):
        with patch.object(hc.subprocess, "run", side_effect=[_P(0, "/some/path"), _P(0, "false")]):
            c = hc.check_git_config("/tmp")
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("stray git configuration found", c["detail"])
        self.assertIn("core.worktree=/some/path", c["detail"])
        self.assertIn("git-repair", c["fix"])

    def test_stray_bare_true(self):
        with patch.object(hc.subprocess, "run", side_effect=[_P(1), _P(0, "true")]):
            c = hc.check_git_config("/tmp")
        self.assertEqual(c["status"], hc.WARN)
        self.assertIn("stray git configuration found", c["detail"])
        self.assertIn("core.bare=true", c["detail"])
        self.assertIn("git-repair", c["fix"])


if __name__ == "__main__":
    unittest.main()
