import contextlib
import io
import os
import tempfile
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module():
    import solomon_harness.skills as skills
    return skills


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

    def test_discover_is_deterministic_on_duplicate_stems(self):
        # Two different paths map to the same stem "dup".
        for top in ("b-dir", "a-dir"):
            os.makedirs(os.path.join(self.root, top, "skills"))
            with open(os.path.join(self.root, top, "skills", "dup.md"), "w", encoding="utf-8") as f:
                f.write(f"# {top}")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            first = self.mod.discover_skill_files(self.root)
        second = self.mod.discover_skill_files(self.root)

        # Sorted traversal makes "a-dir" win deterministically across runs.
        self.assertEqual(first, second)
        self.assertEqual(first["dup"], os.path.join(self.root, "a-dir", "skills", "dup.md"))
        warning = stderr.getvalue()
        self.assertIn("dup", warning)
        self.assertIn(os.path.join("a-dir", "skills", "dup.md"), warning)
        self.assertIn(os.path.join("b-dir", "skills", "dup.md"), warning)

    def test_install_skill_md_folder_copies_siblings(self):
        pkg = os.path.join(self.root, "packaged-skill")
        os.makedirs(os.path.join(pkg, "assets"))
        with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Packaged")
        with open(os.path.join(pkg, "helper.py"), "w", encoding="utf-8") as f:
            f.write("print('hi')\n")
        with open(os.path.join(pkg, "assets", "data.txt"), "w", encoding="utf-8") as f:
            f.write("payload")

        skills_dir = os.path.join(self.root, "agents", "qa", "skills")
        target = self.mod.install_skill(os.path.join(pkg, "SKILL.md"), skills_dir, "packaged-skill")

        self.assertTrue(os.path.isdir(target))
        self.assertTrue(os.path.isfile(os.path.join(target, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, "helper.py")))
        self.assertTrue(os.path.isfile(os.path.join(target, "assets", "data.txt")))

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
