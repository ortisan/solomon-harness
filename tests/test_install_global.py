import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from solomon_harness import install_global as ig


def _make_source(root):
    """Build a minimal package-like source tree for the installer to copy from."""
    os.makedirs(os.path.join(root, "agents", "qa", "agents"))
    with open(os.path.join(root, "agents", "qa", "agents", "qa.md"), "w") as f:
        f.write("# qa")
    with open(os.path.join(root, "docker-compose.yml"), "w") as f:
        f.write("services: {}\n")
    os.makedirs(os.path.join(root, ".claude", "agents"))
    for n in ("qa.md", "sre.md"):
        with open(os.path.join(root, ".claude", "agents", n), "w") as f:
            f.write(f"# {n}")
    os.makedirs(os.path.join(root, ".claude", "commands"))
    with open(os.path.join(root, ".claude", "commands", "solomon-workflow.md"), "w") as f:
        f.write("# workflow")
    os.makedirs(os.path.join(root, ".gemini", "commands"))
    with open(os.path.join(root, ".gemini", "commands", "solomon-workflow.toml"), "w") as f:
        f.write("prompt = 'x'")


class TestInstallGlobal(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.TemporaryDirectory()
        self.dst = tempfile.TemporaryDirectory()
        _make_source(self.src.name)
        self.claude = os.path.join(self.dst.name, ".claude")
        self.gemini = os.path.join(self.dst.name, ".gemini")
        self.home = os.path.join(self.dst.name, ".solomon-harness")

    def tearDown(self):
        self.src.cleanup()
        self.dst.cleanup()

    def _install(self, **kw):
        return ig.install_global(
            source_root=self.src.name,
            claude_dir=self.claude,
            gemini_dir=self.gemini,
            home_dir=self.home,
            register_mcp=False,
            **kw,
        )

    def test_copies_everything_to_global_locations(self):
        res = self._install()
        self.assertTrue(os.path.isdir(os.path.join(self.home, "agents", "qa")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "docker-compose.yml")))
        self.assertEqual(sorted(res["claude_agents"]), ["qa.md", "sre.md"])
        self.assertIn("solomon-workflow.md", res["claude_commands"])
        self.assertIn("solomon-workflow.toml", res["gemini_commands"])
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "agents", "sre.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.gemini, "commands", "solomon-workflow.toml")))

    def test_home_compose_templates_assigned_port(self):
        # The bundled compose has the default 8000 mapping; the install must
        # rewrite it to the assigned host port for this shared home.
        with open(os.path.join(self.src.name, "docker-compose.yml"), "w") as f:
            f.write('    ports:\n      - "8000:8000"\n')
        res = self._install()
        with open(os.path.join(self.home, "docker-compose.yml")) as f:
            content = f.read()
        self.assertIn("memory_port", res)
        self.assertIn(f'"{res["memory_port"]}:8000"', content)

    def test_session_hook_is_added_then_idempotent(self):
        res1 = self._install()
        self.assertTrue(res1["hook_installed"])
        self.assertTrue(res1["gemini_hook_installed"])
        
        # Verify Claude
        settings_path = os.path.join(self.claude, "settings.json")
        with open(settings_path) as f:
            settings = json.load(f)
        cmds = json.dumps(settings["hooks"]["SessionStart"])
        self.assertIn("memory-up", cmds)
        self.assertIn("solomon_harness.cli run", cmds)

        # Verify Gemini
        gemini_settings_path = os.path.join(self.gemini, "settings.json")
        with open(gemini_settings_path) as f:
            gemini_settings = json.load(f)
        gemini_cmds = json.dumps(gemini_settings["hooks"]["SessionStart"])
        self.assertIn("memory-up", gemini_cmds)
        self.assertIn("solomon_harness.cli run", gemini_cmds)

        # Second install must not duplicate the hook.
        res2 = self._install()
        self.assertFalse(res2["hook_installed"])
        self.assertFalse(res2["gemini_hook_installed"])
        with open(settings_path) as f:
            settings2 = json.load(f)
        self.assertEqual(len(settings2["hooks"]["SessionStart"]), 1)
        with open(gemini_settings_path) as f:
            gemini_settings2 = json.load(f)
        self.assertEqual(len(gemini_settings2["hooks"]["SessionStart"]), 1)

    def test_preserves_existing_settings(self):
        os.makedirs(self.claude, exist_ok=True)
        with open(os.path.join(self.claude, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash(git status:*)"]}}, f)
        self._install()
        with open(os.path.join(self.claude, "settings.json")) as f:
            settings = json.load(f)
        self.assertIn("permissions", settings)
        self.assertIn("SessionStart", settings["hooks"])

    def test_reinstall_refreshes_home_agents(self):
        self._install()
        # Drop a stale file into the home agents tree; reinstall must clear it.
        stale = os.path.join(self.home, "agents", "STALE.txt")
        with open(stale, "w") as f:
            f.write("old")
        self._install()
        self.assertFalse(os.path.isfile(stale))

    def test_mcp_registration_best_effort_when_cli_absent(self):
        with patch.object(ig.shutil, "which", return_value=None):
            res = ig.install_global(
                source_root=self.src.name,
                claude_dir=self.claude,
                gemini_dir=self.gemini,
                home_dir=self.home,
                register_mcp=True,
            )
        self.assertIsNone(res["mcp_claude"])

    def test_gemini_extension_installed_with_manifest(self):
        with patch("solomon_harness.install_global.shutil.which", return_value=None):
            res = self._install()
            
        ext_dir = os.path.join(self.gemini, "extensions", "solomon")
        self.assertTrue(os.path.isdir(os.path.join(ext_dir, "commands")))
        self.assertTrue(os.path.isfile(os.path.join(ext_dir, "commands", "solomon-workflow.toml")))
        
        manifest_path = os.path.join(ext_dir, "gemini-extension.json")
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["name"], "solomon")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertTrue(res.get("gemini_extension"))

    def test_agy_import_triggers_on_default_gemini_path(self):
        default_gemini = os.path.expanduser("~/.gemini")
        with (
            patch("solomon_harness.install_global.shutil.which", return_value="/usr/local/bin/agy"),
            patch("solomon_harness.install_global.subprocess.run") as mock_run,
        ):
            res = ig.install_global(
                source_root=self.src.name,
                claude_dir=self.claude,
                gemini_dir=default_gemini,
                home_dir=self.home,
                register_mcp=False,
            )
            
            self.assertTrue(res.get("gemini_extension"))
            self.assertTrue(res.get("agy_imported"))
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(args[0], ["/usr/local/bin/agy", "plugin", "import", "gemini", "--force"])

    def test_agy_import_skips_when_agy_absent(self):
        default_gemini = os.path.expanduser("~/.gemini")
        with (
            patch("solomon_harness.install_global.shutil.which", return_value=None),
            patch("solomon_harness.install_global.os.path.isfile", return_value=False),
            patch("solomon_harness.install_global.subprocess.run") as mock_run,
        ):
            res = ig.install_global(
                source_root=self.src.name,
                claude_dir=self.claude,
                gemini_dir=default_gemini,
                home_dir=self.home,
                register_mcp=False,
            )
            self.assertIsNone(res.get("agy_imported"))
            mock_run.assert_not_called()

    def test_describe_formatting(self):
        # Case 1: All values present
        res_val = {
            "memory_port": 8099,
            "home_agents": True,
            "home_compose": True,
            "claude_agents": ["qa.md"],
            "claude_commands": ["cmd1"],
            "gemini_commands": ["cmd2"],
            "gemini_extension": True,
            "agy_imported": True,
            "hook_installed": True,
            "gemini_hook_installed": True,
            "mcp_claude": True,
            "mcp_gemini": True,
        }
        summary = ig.describe(res_val)
        self.assertIn("SurrealDB host port 8099", summary)
        self.assertIn("successfully imported and converted", summary)
        self.assertIn("session hook (claude): installed", summary)
        self.assertIn("session hook (gemini): installed", summary)
        self.assertIn("MCP (claude, user scope): registered", summary)
        self.assertIn("MCP (gemini, user scope): registered", summary)

        # Case 2: MCPs missing (None) and agy failed
        res_val2 = {
            "gemini_extension": True,
            "agy_imported": False,
            "hook_installed": False,
            "gemini_hook_installed": False,
            "mcp_claude": None,
            "mcp_gemini": None,
        }
        summary2 = ig.describe(res_val2)
        self.assertIn("import run failed", summary2)
        self.assertIn("session hook (claude): already present", summary2)
        self.assertIn("MCP (claude): claude CLI not found", summary2)
        self.assertIn("MCP (gemini): gemini CLI not found", summary2)

        # Case 3: agy_imported is None and gemini_extension is True
        res_val3 = {
            "gemini_extension": True,
            "agy_imported": None,
        }
        summary3 = ig.describe(res_val3)
        self.assertIn("agy CLI not found or non-default path", summary3)

    def test_merge_settings_hook_json_decode_error(self):
        settings_path = os.path.join(self.claude, "settings.json")
        os.makedirs(self.claude, exist_ok=True)
        with open(settings_path, "w") as f:
            f.write("{invalid_json")
        res = ig._merge_session_start_hook(settings_path)
        self.assertTrue(res)
        with open(settings_path) as f:
            settings = json.load(f)
        self.assertIn("hooks", settings)

    def test_merge_settings_hook_permission_error(self):
        settings_path = os.path.join(self.claude, "settings.json")
        os.makedirs(self.claude, exist_ok=True)
        with open(settings_path, "w") as f:
            f.write("{}")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            res = ig._merge_session_start_hook(settings_path)
            self.assertFalse(res)

    def test_register_mcp_success_and_failure(self):
        with (
            patch("solomon_harness.install_global.shutil.which", return_value="/usr/bin/claude"),
            patch("solomon_harness.install_global.subprocess.run") as mock_run,
        ):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_run.return_value = mock_proc
            
            res_ok = ig._register_mcp(["args"], "claude")
            self.assertTrue(res_ok)
            
            mock_proc.returncode = 1
            res_fail = ig._register_mcp(["args"], "claude")
            self.assertFalse(res_fail)

    def test_register_mcp_exception(self):
        with (
            patch("solomon_harness.install_global.shutil.which", return_value="/usr/bin/claude"),
            patch("solomon_harness.install_global.subprocess.run", side_effect=RuntimeError("exec error")),
        ):
            res = ig._register_mcp(["args"], "claude")
            self.assertFalse(res)

    def test_install_global_agy_fallback_and_exception(self):
        from os.path import isfile as real_isfile
        default_gemini = os.path.expanduser("~/.gemini")
        def custom_isfile(path):
            if "agy" in str(path):
                return True
            return real_isfile(path)
            
        with (
            patch("solomon_harness.install_global.shutil.which", return_value=None),
            patch("solomon_harness.install_global.os.path.isfile", side_effect=custom_isfile),
            patch("solomon_harness.install_global.os.access", return_value=True),
            patch("solomon_harness.install_global.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0)]
            res = ig.install_global(
                source_root=self.src.name,
                claude_dir=self.claude,
                gemini_dir=default_gemini,
                home_dir=self.home,
                register_mcp=False,
            )
            self.assertTrue(res.get("agy_imported"))
            
            # Exception scenario
            mock_run.side_effect = RuntimeError("import failed")
            res_exc = ig.install_global(
                source_root=self.src.name,
                claude_dir=self.claude,
                gemini_dir=default_gemini,
                home_dir=self.home,
                register_mcp=False,
            )
            self.assertFalse(res_exc.get("agy_imported"))


if __name__ == "__main__":
    unittest.main()

