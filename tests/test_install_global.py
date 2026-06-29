import json
import os
import tempfile
import unittest
from unittest.mock import patch

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
    with open(os.path.join(root, ".claude", "commands", "solomon-loop.md"), "w") as f:
        f.write("# loop")
    os.makedirs(os.path.join(root, ".gemini", "commands"))
    with open(os.path.join(root, ".gemini", "commands", "solomon-loop.toml"), "w") as f:
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
        self.assertIn("solomon-loop.md", res["claude_commands"])
        self.assertIn("solomon-loop.toml", res["gemini_commands"])
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "agents", "sre.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.gemini, "commands", "solomon-loop.toml")))

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
        self.assertTrue(os.path.isfile(os.path.join(ext_dir, "commands", "solomon-loop.toml")))
        
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


if __name__ == "__main__":
    unittest.main()

