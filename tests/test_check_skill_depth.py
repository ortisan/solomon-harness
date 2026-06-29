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


if __name__ == "__main__":
    unittest.main()
