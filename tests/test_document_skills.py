import importlib.util
import os
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "document-skills.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("document_skills", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDocumentSkills(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text):
        path = os.path.join(self.dir, "skill.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_strips_leading_bullet_marker(self):
        path = self._write(
            "## Clean code\n\n- Functions do one thing at one level of abstraction.\n"
        )
        _, purpose = self.mod.extract_metadata(path)
        self.assertFalse(purpose.startswith("- "))
        self.assertTrue(purpose.startswith("Functions do one thing"))

    def test_strips_leading_checkbox_marker(self):
        path = self._write("# Done\n\n- [ ] A failing test existed first.\n")
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "A failing test existed first.")

    def test_prefers_purpose_line(self):
        path = self._write(
            "# OAuth\n\nPurpose: Implement OAuth flows.\n\nMore detail follows here.\n"
        )
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "Implement OAuth flows.")

    def test_caps_long_paragraph(self):
        long_line = (
            "This skill describes a great many considerations that an engineer "
            "must weigh carefully across modules and boundaries without ever "
            "reaching a sentence terminator anywhere close to the start"
        )
        path = self._write("# Long\n\n" + long_line + "\n")
        _, purpose = self.mod.extract_metadata(path)
        self.assertTrue(purpose.endswith("…"))
        # Body (without the single ellipsis char) stays within the cap.
        self.assertLessEqual(len(purpose[:-1]), 140)
        self.assertLess(len(purpose), len(long_line))

    def test_collapses_internal_whitespace(self):
        path = self._write("# Spaces\n\nThis   text\thas     extra   spaces.\n")
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "This text has extra spaces.")
        self.assertNotIn("  ", purpose)
        self.assertNotIn("\t", purpose)

    def test_missing_body_falls_back(self):
        path = self._write("# Only a title\n")
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "No description provided.")

    def test_prefers_frontmatter_description(self):
        path = self._write(
            "---\n"
            "name: oauth\n"
            "description: Implements OAuth flows end to end. Use when wiring login.\n"
            "---\n"
            "# OAuth\n\nThe body says something else entirely.\n"
        )
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "Implements OAuth flows end to end.")

    def test_frontmatter_block_is_not_mistaken_for_body(self):
        # A frontmatter block without a description must be skipped, never
        # surfaced as the first body line.
        path = self._write(
            "---\nname: oauth\n---\n# OAuth\n\nImplement OAuth flows.\n"
        )
        _, purpose = self.mod.extract_metadata(path)
        self.assertEqual(purpose, "Implement OAuth flows.")

    def test_title_still_comes_from_heading_with_frontmatter(self):
        path = self._write(
            "---\nname: oauth\ndescription: Does OAuth. Use when needed.\n---\n"
            "# OAuth Flows\n\nBody.\n"
        )
        title, _ = self.mod.extract_metadata(path)
        self.assertEqual(title, "OAuth Flows")


if __name__ == "__main__":
    unittest.main()
