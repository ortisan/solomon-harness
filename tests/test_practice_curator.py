"""Structure and canonical-depth checks for the practice_curator agent (issue #18).

These encode the testable acceptance criteria of slice 1/4 of epic #16: the agent
definition exists and follows the module pattern, every skill clears the
canonical-depth proxy (>= 600 words, both required sections), the profile lists
every skill, and the safety-relevant guidance (no edits to other agents, the
>= 2-sources rule) is present in the skills that own it.
"""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(REPO, "agents", "practice_curator")
SKILLS_DIR = os.path.join(AGENT_DIR, "skills")
PROFILE = os.path.join(AGENT_DIR, "agents", "practice_curator.md")
PERSONA = os.path.join(AGENT_DIR, "persona.md")
CONFIG = os.path.join(AGENT_DIR, ".agent", "config.json")

EXPECTED_SKILLS = [
    "auditing_delivered_work.md",
    "sourcing_the_state_of_the_art.md",
    "benchmarking_across_domains.md",
    "scope_and_non_negotiables.md",
]

REQUIRED_SECTIONS = ["## Common pitfalls", "## Definition of done"]
MIN_WORDS = 600

# Same banned list as scripts/validate-agents.py, kept local so this test fails
# independently if a cliche slips into the new agent's files.
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
        self.assertEqual(config.get("agent_name"), "practice_curator")


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
        for token in ("practice curator", "state of the art", "best practices",
                      "gap report", "reviewed", "sources"):
            self.assertIn(token, lower, f"profile missing role token '{token}'")


class TestSafetyGuidance(unittest.TestCase):
    def test_audit_skill_forbids_editing_other_agents(self):
        lower = _read(os.path.join(SKILLS_DIR, "auditing_delivered_work.md")).lower()
        self.assertIn("never modifies", lower)
        self.assertIn("other agent", lower)

    def test_sourcing_skill_requires_two_dated_sources(self):
        lower = _read(os.path.join(SKILLS_DIR, "sourcing_the_state_of_the_art.md")).lower()
        self.assertIn("at least two", lower)
        self.assertIn("sources", lower)
        self.assertIn("credib", lower)

    def test_scope_skill_bounds_one_agent_per_change(self):
        lower = _read(os.path.join(SKILLS_DIR, "scope_and_non_negotiables.md")).lower()
        self.assertIn("one agent", lower)
        self.assertIn("human approval", lower)


if __name__ == "__main__":
    unittest.main()
