"""Structure and canonical-depth checks for the research_analyst agent (issue #71).

These encode the testable acceptance criteria of slice 1 of the research_analyst
epic: the agent definition exists and follows the module pattern, every skill clears
the canonical-depth proxy (>= 600 words, both required sections, a versioned/dated
standard), the profile lists every skill and states the role, and the non-negotiable
boundaries (quant_trader / ml_engineer delegation, the security data-not-instructions
rule, the sourced/timestamped not-financial-advice discipline) are present in the
skill that owns them.

Run with: uv run python -m unittest tests.test_research_analyst
(the suite is unittest-based; pytest is not yet a dev dependency — issues #31/#41).
"""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(REPO, "agents", "research_analyst")
SKILLS_DIR = os.path.join(AGENT_DIR, "skills")
PROFILE = os.path.join(AGENT_DIR, "agents", "research_analyst.md")
PERSONA = os.path.join(AGENT_DIR, "persona.md")
CONFIG = os.path.join(AGENT_DIR, ".agent", "config.json")

EXPECTED_SKILLS = [
    "research_sources_playbook.md",
    "valuation_methods.md",
    "scope_and_non_negotiables.md",
    "common_pitfalls.md",
    "definition_of_done.md",
]

REQUIRED_SECTIONS = ["## Common pitfalls", "## Definition of done"]
MIN_WORDS = 600

# A versioned/dated standard reference: "1.2", "2.x", a 19xx/20xx year, or an RFC number.
VERSION_RE = re.compile(r"\b\d+\.\d+|\b\d+\.x\b|\b(?:19|20)\d{2}\b|\bRFC\s?\d+", re.IGNORECASE)


def _has_emoji(text):
    """Mirror scripts/validate-agents.py emoji ranges; em dash/ellipsis are not flagged."""
    for ch in text:
        cp = ord(ch)
        if (0x1F000 <= cp <= 0x1FFFF) or (0x2600 <= cp <= 0x27BF) or (0x2300 <= cp <= 0x23FF):
            return True
    return False


# Same banned list as scripts/validate-agents.py, kept local so this test fails
# independently if a cliche slips into the new agent's files. "leverage" is the
# finance trap: phrase it as "financial leverage ratio", "gearing", or "debt load".
CLICHES = [
    "delve", "leverage", "testament", "dive into", "feel free",
    "in summary", "moreover", "firstly", "secondly", "lastly",
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestStructure(unittest.TestCase):
    def test_core_files_exist(self):
        for path in (PERSONA, PROFILE, CONFIG):
            self.assertTrue(os.path.isfile(path), f"missing {path}")
        self.assertTrue(os.path.isdir(SKILLS_DIR), "missing skills/ directory")

    def test_expected_skills_exist(self):
        for name in EXPECTED_SKILLS:
            self.assertTrue(
                os.path.isfile(os.path.join(SKILLS_DIR, name)),
                f"missing skill {name}",
            )

    def test_config_is_valid_and_named(self):
        config = json.loads(_read(CONFIG))
        self.assertEqual(config.get("agent_name"), "research_analyst")


class TestDepth(unittest.TestCase):
    def _skill_files(self):
        return [
            os.path.join(SKILLS_DIR, n)
            for n in sorted(os.listdir(SKILLS_DIR))
            if n.endswith(".md")
        ]

    def test_each_skill_meets_the_depth_proxy(self):
        for path in self._skill_files():
            text = _read(path)
            words = len(re.findall(r"\S+", text))
            self.assertGreaterEqual(
                words, MIN_WORDS, f"{os.path.basename(path)} has {words} words (< {MIN_WORDS})"
            )
            for section in REQUIRED_SECTIONS:
                self.assertIn(
                    section, text, f"{os.path.basename(path)} missing section '{section}'"
                )

    def test_each_skill_names_a_versioned_standard(self):
        for path in self._skill_files():
            self.assertRegex(
                _read(path),
                VERSION_RE,
                f"{os.path.basename(path)} names no standard/library/framework with a version",
            )

    def test_no_cliches_in_agent_files(self):
        files = [PERSONA, PROFILE] + self._skill_files()
        for path in files:
            lower = _read(path).lower()
            for cliche in CLICHES:
                self.assertNotIn(
                    cliche, lower, f"cliche '{cliche}' found in {os.path.basename(path)}"
                )


class TestProfileListsSkills(unittest.TestCase):
    def test_profile_lists_every_skill(self):
        profile = _read(PROFILE)
        for name in sorted(os.listdir(SKILLS_DIR)):
            if name.endswith(".md"):
                self.assertIn(
                    f"skills/{name}", profile, f"profile does not list {name}"
                )

    def test_profile_states_the_role(self):
        lower = _read(PROFILE).lower()
        for token in ("research analyst", "valuation", "investment", "sources", "quant_trader"):
            self.assertIn(token, lower, f"profile missing role token '{token}'")


class TestBoundaryGuidance(unittest.TestCase):
    def test_scope_skill_encodes_the_specialist_and_safety_boundaries(self):
        lower = _read(os.path.join(SKILLS_DIR, "scope_and_non_negotiables.md")).lower()
        # Specialist delegation boundaries.
        self.assertIn("quant_trader", lower)
        self.assertIn("ml_engineer", lower)
        # Security: untrusted-content-as-data (STRIDE Tampering / prompt injection).
        self.assertIn("treated as data", lower)
        self.assertIn("never executed as instructions", lower)
        # Sourcing and the not-advice discipline (product_owner).
        self.assertIn("not financial advice", lower)
        self.assertIn("timestamp", lower)
        self.assertIn("source", lower)

    def test_sources_playbook_names_the_tools_and_edgar(self):
        lower = _read(os.path.join(SKILLS_DIR, "research_sources_playbook.md")).lower()
        for token in ("websearch", "webfetch", "claude-in-chrome", "solomon-memory", "sec edgar"):
            self.assertIn(token, lower, f"sources playbook missing '{token}'")

    def test_valuation_skill_delegates_quant_claims(self):
        lower = _read(os.path.join(SKILLS_DIR, "valuation_methods.md")).lower()
        self.assertIn("quant_trader", lower)


class TestNoEmoji(unittest.TestCase):
    def test_persona_bans_emojis(self):
        self.assertIn("no emojis", _read(PERSONA).lower())

    def test_no_emoji_chars_in_agent_files(self):
        files = [PERSONA, PROFILE] + [
            os.path.join(SKILLS_DIR, n)
            for n in sorted(os.listdir(SKILLS_DIR))
            if n.endswith(".md")
        ]
        for path in files:
            self.assertFalse(
                _has_emoji(_read(path)),
                f"emoji codepoint found in {os.path.basename(path)}",
            )


if __name__ == "__main__":
    unittest.main()
