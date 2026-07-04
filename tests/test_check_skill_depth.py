import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-skill-depth.py")

# A canonical closing block: both required sections present.
SECTIONS = "\n## Common pitfalls\n\n- A pitfall, with its reason.\n\n## Definition of done\n\n- [ ] Done.\n"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_skill_depth", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCheckSkillDepth(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text):
        path = self.dir / "skill.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_word_count_counts_non_whitespace_tokens(self):
        self.assertEqual(self.mod.word_count("one two\tthree\nfour"), 4)

    def test_compliant_file_has_no_gaps(self):
        body = "# Skill\n\nA sharp summary sentence.\n\n" + ("word " * 600) + SECTIONS
        self.assertEqual(self.mod.check_skill(self._write(body)), [])

    def test_short_file_flags_word_count(self):
        gaps = self.mod.check_skill(self._write("# Skill\n\nShort body." + SECTIONS))
        self.assertTrue(any(f"{self.mod.MIN_WORDS}w" in g for g in gaps))

    def test_missing_common_pitfalls_is_flagged(self):
        body = "# Skill\n\n" + ("word " * 600) + "\n## Definition of done\n\n- [ ] Done.\n"
        gaps = self.mod.check_skill(self._write(body))
        self.assertTrue(any("Common pitfalls" in g for g in gaps))

    def test_missing_definition_of_done_is_flagged(self):
        body = "# Skill\n\n" + ("word " * 600) + "\n## Common pitfalls\n\n- A pitfall.\n"
        gaps = self.mod.check_skill(self._write(body))
        self.assertTrue(any("Definition of done" in g for g in gaps))

    def test_invalid_agent_name_is_rejected(self):
        # A path-traversal or absolute-path argument must not redirect the scan.
        self.assertEqual(self.mod.main(["../etc"]), 1)
        self.assertEqual(self.mod.main(["software_architect/../.."]), 1)

    def test_compliant_agents_pass(self):
        # On this branch the architect and sre role-core skills meet the bar,
        # so the happy path of main() returns 0.
        self.assertEqual(self.mod.main(["software_architect", "sre"]), 0)


class TestCheckSkillFormat(unittest.TestCase):
    """The repo-wide format gate: every agents/*/skills/*.md must carry both
    mandated sections and a snake_case filename (agents/AGENTS.md, "Skill file
    format"). Unlike the depth bar, no file is exempt."""

    COMPLIANT = "# Skill\n\nA sharp summary sentence." + SECTIONS

    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def _skill(self, root, agent, name, text):
        skills = root / "agents" / agent / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / name).write_text(text, encoding="utf-8")

    def test_compliant_file_has_no_format_gaps(self):
        self.assertEqual(self.mod.check_format(self._write("skill.md", self.COMPLIANT)), [])

    def test_missing_sections_are_flagged(self):
        gaps = self.mod.check_format(self._write("skill.md", "# Skill\n\nBody only.\n"))
        self.assertTrue(any("Common pitfalls" in g for g in gaps))
        self.assertTrue(any("Definition of done" in g for g in gaps))

    def test_hyphenated_filename_is_flagged(self):
        gaps = self.mod.check_format(self._write("oauth2-oidc.md", self.COMPLIANT))
        self.assertTrue(any("snake_case" in g for g in gaps))

    def test_uppercase_filename_is_flagged(self):
        gaps = self.mod.check_format(self._write("OAuth2.md", self.COMPLIANT))
        self.assertTrue(any("snake_case" in g for g in gaps))

    def test_scan_format_reports_each_violation(self):
        self._skill(self.dir, "alpha", "good_skill.md", self.COMPLIANT)
        self._skill(self.dir, "alpha", "bad-name.md", self.COMPLIANT)
        self._skill(self.dir, "beta", "no_sections.md", "# Skill\n\nBody only.\n")
        failures = self.mod.scan_format(self.dir)
        self.assertEqual(len(failures), 2)
        self.assertTrue(any("bad-name.md" in f for f in failures))
        self.assertTrue(any("no_sections.md" in f for f in failures))

    def test_scan_format_passes_on_compliant_tree(self):
        self._skill(self.dir, "alpha", "good_skill.md", self.COMPLIANT)
        self.assertEqual(self.mod.scan_format(self.dir), [])

    def test_main_fails_on_format_violation_anywhere(self):
        # Build a tree whose default depth agents pass the bar, then plant a
        # single format violation in a third agent: main() must return 1.
        deep = "# Skill\n\nA sharp summary sentence.\n\n" + ("word " * 600) + SECTIONS
        for agent in self.mod.DEFAULT_AGENTS:
            self._skill(self.dir, agent, "core_skill.md", deep)
        self._skill(self.dir, "gamma", "bad-name.md", self.COMPLIANT)
        original = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = self.dir
            self.assertEqual(self.mod.main([]), 1)
            (self.dir / "agents" / "gamma" / "skills" / "bad-name.md").rename(
                self.dir / "agents" / "gamma" / "skills" / "good_name.md"
            )
            self.assertEqual(self.mod.main([]), 0)
        finally:
            self.mod.REPO_ROOT = original

    def test_repo_skills_tree_is_format_clean(self):
        # The gate this branch enforces: the real tree has no violations left.
        self.assertEqual(self.mod.scan_format(Path(REPO)), [])


if __name__ == "__main__":
    unittest.main()
