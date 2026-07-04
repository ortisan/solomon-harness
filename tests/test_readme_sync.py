"""README.md must not silently drift from the CLI, the agent roster, and the
`/solomon-*` command set it documents.

These checks introspect the real sources of truth (``solomon_harness.cli.build_parser()``,
the ``agents/`` directory, and ``.claude/commands/``) instead of hand-counting, so
the same drift this test caught once (a CLI table missing more than half the
subcommands, and stale "nineteen agents" / "seven commands" counts) cannot
recur without failing CI.
"""

import glob
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")

_ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _number_word(n: int) -> str:
    """Spell out an integer 0-99 the way the README does ("Twenty-four")."""
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"


def _cli_subcommands():
    """The live top-level subcommand names from solomon_harness.cli.build_parser()."""
    import argparse

    from solomon_harness.cli import build_parser

    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices.keys())
    raise AssertionError("build_parser() has no subparsers action")


def _agent_names():
    """Every agent under agents/ that has a role profile agents/<name>/agents/<name>.md."""
    agents_dir = os.path.join(REPO, "agents")
    names = []
    for entry in sorted(os.listdir(agents_dir)):
        profile = os.path.join(agents_dir, entry, "agents", f"{entry}.md")
        if os.path.isfile(profile):
            names.append(entry)
    return names


def _solomon_command_files():
    return sorted(glob.glob(os.path.join(REPO, ".claude", "commands", "solomon-*.md")))


def _readme_text():
    with open(README, "r", encoding="utf-8") as f:
        return f.read()


def _cli_reference_table_commands(text):
    """Command tokens from the first column of the '### `solomon-harness`' table."""
    section = text.split("### `solomon-harness`", 1)[1]
    section = section.split("\n---", 1)[0]
    commands = []
    for line in section.splitlines():
        match = re.match(r"\|\s*`([a-z][a-z-]*)", line)
        if match:
            commands.append(match.group(1))
    return commands


class TestReadmeAgentCount(unittest.TestCase):
    def test_stated_agent_count_matches_agents_directory(self):
        actual = len(_agent_names())
        text = _readme_text()
        expected_word = _number_word(actual).capitalize()
        self.assertIn(
            f"{expected_word} role-specific agents",
            text,
            f"README should state '{expected_word} role-specific agents' to match "
            f"the {actual} agents/*/agents/*.md profiles on disk",
        )

    def test_agent_table_lists_every_agent(self):
        text = _readme_text()
        table = text.split("### Specialist agents", 1)[1].split("### Skills", 1)[0]
        for name in _agent_names():
            self.assertIn(
                f"`{name}`", table, f"agent '{name}' is missing from the README agent table"
            )


class TestReadmeCommandCount(unittest.TestCase):
    def test_stated_solomon_command_count_matches_command_files(self):
        actual = len(_solomon_command_files())
        text = _readme_text()
        expected_word = _number_word(actual).capitalize()
        self.assertIn(
            f"{expected_word} `/solomon-*` commands",
            text,
            f"README should state '{expected_word} `/solomon-*` commands' to match "
            f"the {actual} files under .claude/commands/solomon-*.md",
        )


class TestReadmeCliReference(unittest.TestCase):
    def test_cli_table_lists_every_subcommand_exactly_once(self):
        text = _readme_text()
        documented = _cli_reference_table_commands(text)
        actual = _cli_subcommands()

        missing = [c for c in actual if c not in documented]
        extra = [c for c in documented if c not in actual]

        self.assertEqual(missing, [], f"CLI subcommands missing from README table: {missing}")
        self.assertEqual(extra, [], f"README table documents commands cli.py no longer has: {extra}")
        self.assertEqual(
            len(documented), len(set(documented)), "CLI reference table has a duplicate row"
        )


if __name__ == "__main__":
    unittest.main()
