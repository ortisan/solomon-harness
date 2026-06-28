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

    def test_session_hook_is_added_then_idempotent(self):
        res1 = self._install()
        self.assertTrue(res1["hook_installed"])
        settings_path = os.path.join(self.claude, "settings.json")
        with open(settings_path) as f:
            settings = json.load(f)
        cmds = json.dumps(settings["hooks"]["SessionStart"])
        self.assertIn("memory-up", cmds)
        self.assertIn("solomon_harness.cli run", cmds)

        # Second install must not duplicate the hook.
        res2 = self._install()
        self.assertFalse(res2["hook_installed"])
        with open(settings_path) as f:
            settings2 = json.load(f)
        self.assertEqual(len(settings2["hooks"]["SessionStart"]), 1)

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


if __name__ == "__main__":
    unittest.main()
