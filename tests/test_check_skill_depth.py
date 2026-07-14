import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-skill-depth.py")

# A canonical closing block: both required sections present.
SECTIONS = "\n## Common pitfalls\n\n- A pitfall, with its reason.\n\n## Definition of done\n\n- [ ] Done.\n"


def _frontmatter(stem, description="Does the thing well. Use when testing the gate."):
    """Compliant frontmatter for a skill file named <stem>.md."""
    name = stem.replace("_", "-")
    return f"---\nname: {name}\ndescription: {description}\n---\n"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_skill_depth", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParseFrontmatter(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_splits_fields_and_body(self):
        fields, body = self.mod.parse_frontmatter(
            "---\nname: a-skill\ndescription: Does A. Use when B.\n---\n# Title\n\nBody.\n"
        )
        self.assertEqual(fields["name"], "a-skill")
        self.assertEqual(fields["description"], "Does A. Use when B.")
        self.assertTrue(body.startswith("# Title"))

    def test_no_frontmatter_returns_full_text(self):
        fields, body = self.mod.parse_frontmatter("# Title\n\nBody.\n")
        self.assertEqual(fields, {})
        self.assertTrue(body.startswith("# Title"))

    def test_unterminated_block_is_not_frontmatter(self):
        fields, body = self.mod.parse_frontmatter("---\nname: a\nno closing fence\n")
        self.assertEqual(fields, {})
        self.assertTrue(body.startswith("---"))


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

    def test_frontmatter_does_not_count_toward_depth(self):
        # 550 body words + a long frontmatter block must still fail the bar:
        # only the body carries the depth.
        padding = "pad " * 80
        body = (
            _frontmatter("skill", "Does X. Use when Y. " + padding)
            + "# Skill\n\n"
            + ("word " * 550)
            + SECTIONS
        )
        gaps = self.mod.check_skill(self._write(body))
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

    def test_default_agents_discovers_every_skills_dir(self):
        # With no arguments the depth scan covers the whole roster, not a
        # hand-picked subset: every agents/*/skills directory is a target.
        (self.dir / "agents" / "alpha" / "skills").mkdir(parents=True)
        (self.dir / "agents" / "beta" / "skills").mkdir(parents=True)
        (self.dir / "agents" / "not_an_agent").mkdir(parents=True)
        original = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = self.dir
            self.assertEqual(self.mod.default_agents(), ["alpha", "beta"])
        finally:
            self.mod.REPO_ROOT = original


class TestCheckSkillFormat(unittest.TestCase):
    """The repo-wide format gate: every agents/*/skills/*.md must carry both
    mandated sections, a snake_case filename, and discovery frontmatter with a
    matching name and a 'Use when' description (agents/AGENTS.md, "Skill file
    format"). Unlike the depth bar, no file is exempt."""

    BODY = "# Skill\n\nA sharp summary sentence." + SECTIONS

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

    def _skill(self, root, agent, name, text=None):
        skills = root / "agents" / agent / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        if text is None:
            text = _frontmatter(name[:-3]) + self.BODY
        (skills / name).write_text(text, encoding="utf-8")

    def test_compliant_file_has_no_format_gaps(self):
        path = self._write("skill.md", _frontmatter("skill") + self.BODY)
        self.assertEqual(self.mod.check_format(path), [])

    def test_missing_frontmatter_is_flagged(self):
        gaps = self.mod.check_format(self._write("skill.md", self.BODY))
        self.assertTrue(any("frontmatter" in g for g in gaps))

    def test_frontmatter_name_must_match_filename(self):
        text = "---\nname: other-name\ndescription: Does X. Use when Y.\n---\n" + self.BODY
        gaps = self.mod.check_format(self._write("skill.md", text))
        self.assertTrue(any("name" in g for g in gaps))

    def test_underscored_stem_maps_to_hyphenated_name(self):
        path = self._write("data_wrangling.md", _frontmatter("data_wrangling") + self.BODY)
        self.assertEqual(self.mod.check_format(path), [])

    def test_empty_description_is_flagged(self):
        text = "---\nname: skill\ndescription:\n---\n" + self.BODY
        gaps = self.mod.check_format(self._write("skill.md", text))
        self.assertTrue(any("description" in g for g in gaps))

    def test_description_without_use_when_trigger_is_flagged(self):
        text = "---\nname: skill\ndescription: Does the thing well.\n---\n" + self.BODY
        gaps = self.mod.check_format(self._write("skill.md", text))
        self.assertTrue(any("Use when" in g for g in gaps))

    def test_description_over_1024_chars_is_flagged(self):
        long_desc = "Does X. Use when Y. " + ("pad " * 300)
        text = f"---\nname: skill\ndescription: {long_desc}\n---\n" + self.BODY
        gaps = self.mod.check_format(self._write("skill.md", text))
        self.assertTrue(any("1024" in g for g in gaps))

    def test_missing_sections_are_flagged(self):
        gaps = self.mod.check_format(self._write("skill.md", "# Skill\n\nBody only.\n"))
        self.assertTrue(any("Common pitfalls" in g for g in gaps))
        self.assertTrue(any("Definition of done" in g for g in gaps))

    def test_hyphenated_filename_is_flagged(self):
        path = self._write("oauth2-oidc.md", _frontmatter("oauth2-oidc") + self.BODY)
        gaps = self.mod.check_format(path)
        self.assertTrue(any("snake_case" in g for g in gaps))

    def test_uppercase_filename_is_flagged(self):
        path = self._write("OAuth2.md", _frontmatter("oauth2") + self.BODY)
        gaps = self.mod.check_format(path)
        self.assertTrue(any("snake_case" in g for g in gaps))

    def test_scan_format_reports_each_violation(self):
        self._skill(self.dir, "alpha", "good_skill.md")
        self._skill(self.dir, "alpha", "bad-name.md", _frontmatter("bad-name") + self.BODY)
        self._skill(self.dir, "beta", "no_sections.md", "# Skill\n\nBody only.\n")
        failures = self.mod.scan_format(self.dir)
        self.assertEqual(len(failures), 2)
        self.assertTrue(any("bad-name.md" in f for f in failures))
        self.assertTrue(any("no_sections.md" in f for f in failures))

    def test_scan_format_passes_on_compliant_tree(self):
        self._skill(self.dir, "alpha", "good_skill.md")
        self.assertEqual(self.mod.scan_format(self.dir), [])

    def test_main_fails_on_format_violation_anywhere(self):
        # Build a tree whose skills pass the depth bar, then plant a single
        # format violation: main() must return 1 until it is fixed.
        deep = "# Skill\n\nA sharp summary sentence.\n\n" + ("word " * 600) + SECTIONS
        self._skill(self.dir, "alpha", "core_skill.md", _frontmatter("core_skill") + deep)
        self._skill(self.dir, "gamma", "bad-name.md", _frontmatter("bad-name") + deep)
        original = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = self.dir
            self.assertEqual(self.mod.main([]), 1)
            bad = self.dir / "agents" / "gamma" / "skills" / "bad-name.md"
            good = self.dir / "agents" / "gamma" / "skills" / "good_name.md"
            bad.rename(good)
            good.write_text(_frontmatter("good_name") + deep, encoding="utf-8")
            self.assertEqual(self.mod.main([]), 0)
        finally:
            self.mod.REPO_ROOT = original

    def test_scope_and_mandate_is_depth_exempt(self):
        # A freshly scaffolded agent ships a short scope_and_mandate.md; the
        # depth bar must not fail it (it stays format-gated like every file).
        deep = "# Skill\n\nA sharp summary sentence.\n\n" + ("word " * 600) + SECTIONS
        self._skill(self.dir, "alpha", "core_skill.md", _frontmatter("core_skill") + deep)
        self._skill(
            self.dir,
            "newborn",
            "scope_and_mandate.md",
            _frontmatter("scope_and_mandate") + self.BODY,
        )
        original = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = self.dir
            self.assertEqual(self.mod.main([]), 0)
        finally:
            self.mod.REPO_ROOT = original

    def test_main_default_scan_flags_shallow_skill_in_any_agent(self):
        # The depth bar applies to the whole roster by default: a shallow
        # role-core skill in an arbitrary agent fails main([]).
        deep = "# Skill\n\nA sharp summary sentence.\n\n" + ("word " * 600) + SECTIONS
        self._skill(self.dir, "alpha", "core_skill.md", _frontmatter("core_skill") + deep)
        self._skill(self.dir, "gamma", "thin_skill.md", _frontmatter("thin_skill") + self.BODY)
        original = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = self.dir
            self.assertEqual(self.mod.main([]), 1)
        finally:
            self.mod.REPO_ROOT = original

    def test_repo_skills_tree_is_format_clean(self):
        # The gate this branch enforces: the real tree has no violations left.
        self.assertEqual(self.mod.scan_format(Path(REPO)), [])


if __name__ == "__main__":
    unittest.main()
