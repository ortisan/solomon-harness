import importlib.util
import os
import tempfile
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module():
    path = os.path.join(WORKSPACE, "scripts", "fetch-skills.py")
    spec = importlib.util.spec_from_file_location("fetch_skills", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFetchSkills(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_discover_finds_skill_md_folders_and_skills_dir_files(self):
        os.makedirs(os.path.join(self.root, "cool-skill"))
        with open(os.path.join(self.root, "cool-skill", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Cool")
        os.makedirs(os.path.join(self.root, "pkg", "skills"))
        with open(os.path.join(self.root, "pkg", "skills", "oauth2.md"), "w", encoding="utf-8") as f:
            f.write("# OAuth2")

        found = self.mod.discover_skill_files(self.root)
        self.assertIn("cool-skill", found)
        self.assertIn("oauth2", found)

    def test_discover_ignores_git_dir(self):
        os.makedirs(os.path.join(self.root, ".git", "skills"))
        with open(os.path.join(self.root, ".git", "skills", "x.md"), "w", encoding="utf-8") as f:
            f.write("# x")
        self.assertNotIn("x", self.mod.discover_skill_files(self.root))

    def test_install_skill_copies_into_agent_dir(self):
        src = os.path.join(self.root, "src.md")
        with open(src, "w", encoding="utf-8") as f:
            f.write("# Imported skill")
        skills_dir = os.path.join(self.root, "agents", "qa", "skills")
        target = self.mod.install_skill(src, skills_dir, "social-login")
        self.assertTrue(os.path.isfile(target))
        self.assertTrue(target.endswith(os.path.join("skills", "social-login.md")))
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Imported skill")

    def test_load_sources_reads_config(self):
        sources = self.mod.load_sources(WORKSPACE)
        self.assertIn("anthropic-skills", sources)
        self.assertIn("url", sources["anthropic-skills"])


if __name__ == "__main__":
    unittest.main()
