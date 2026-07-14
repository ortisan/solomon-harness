import importlib.util
import os
import unittest

from solomon_harness.frontmatter import split_frontmatter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_script(name):
    path = os.path.join(REPO, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSplitFrontmatter(unittest.TestCase):
    """The single parser behind the CI gate and the profile generator
    (ADR-0026): both consumers must see identical fields and body."""

    def test_splits_fields_and_body(self):
        fields, body = split_frontmatter(
            "---\nname: a-skill\ndescription: Does A. Use when B.\n---\n# Title\n\nBody.\n"
        )
        self.assertEqual(fields["name"], "a-skill")
        self.assertEqual(fields["description"], "Does A. Use when B.")
        self.assertTrue(body.startswith("# Title"))

    def test_no_frontmatter_returns_full_text(self):
        fields, body = split_frontmatter("# Title\n\nBody.\n")
        self.assertEqual(fields, {})
        self.assertTrue(body.startswith("# Title"))

    def test_unterminated_block_is_not_frontmatter(self):
        fields, body = split_frontmatter("---\nname: a\nno closing fence\n")
        self.assertEqual(fields, {})
        self.assertTrue(body.startswith("---"))

    def test_tolerates_trailing_whitespace_on_fences(self):
        fields, body = split_frontmatter(
            "---  \nname: a-skill\ndescription: Does A. Use when B.\n---   \n# Title\n"
        )
        self.assertEqual(fields["name"], "a-skill")
        self.assertTrue(body.startswith("# Title"))

    def test_tolerates_crlf_line_endings(self):
        fields, body = split_frontmatter(
            "---\r\nname: a-skill\r\ndescription: Does A. Use when B.\r\n---\r\n# Title\r\n"
        )
        self.assertEqual(fields["name"], "a-skill")
        self.assertEqual(fields["description"], "Does A. Use when B.")
        self.assertTrue(body.startswith("# Title"))

    def test_field_line_without_colon_is_ignored(self):
        fields, _ = split_frontmatter("---\nname: a\njust words\n---\nBody.\n")
        self.assertEqual(fields, {"name": "a"})


class TestConsumersShareTheParser(unittest.TestCase):
    """Regression guard for the gate/generator divergence: both scripts must
    delegate to solomon_harness.frontmatter, not carry private parsers."""

    EDGE_CASES = [
        "---\nname: x\ndescription: D. Use when E.\n---\nBody.\n",
        "---  \nname: x\n---   \nBody.\n",
        "---\r\nname: x\r\n---\r\nBody.\r\n",
        "---\nunterminated\n",
        "No frontmatter at all.\n",
    ]

    def test_gate_parser_is_the_shared_parser(self):
        gate = _load_script("check-skill-depth.py")
        for text in self.EDGE_CASES:
            self.assertEqual(gate.parse_frontmatter(text), split_frontmatter(text))

    def test_document_skills_uses_the_shared_parser(self):
        docs = _load_script("document-skills.py")
        self.assertIs(docs.split_frontmatter, split_frontmatter)


if __name__ == "__main__":
    unittest.main()
