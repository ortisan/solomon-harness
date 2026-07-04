"""The Review stage's conditional domain lenses: pure path->lens selection.

The mandatory gates (qa, security, software_architect) are constant; these
tests pin the deterministic mapping from changed paths to the extra domain
lenses, the priority order under the cap, the roster-match fitness rule
(ADR-0019: every lens is a deployable agent), and the CLI contract the command
files rely on (`gh pr diff --name-only | python -m solomon_harness.review_roster`).
"""

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from solomon_harness import review_roster

_REPO_ROOT = Path(__file__).resolve().parents[1]

# One representative path per rule, in the module's priority order.
_ALL_DOMAIN_PATHS = [
    "solomon_harness/auth_broker.py",
    "solomon_harness/tools/database_client.py",
    ".github/workflows/release.yml",
    "solomon_harness/loop_lock.py",
    "ui/app/page.tsx",
    "solomon_harness/healthcheck.py",
    "agents/qa/skills/sast.md",
    "docs/solomon-workflow.md",
]


class TestSelectLenses(unittest.TestCase):
    def test_ui_paths_select_frontend(self):
        lenses = review_roster.select_lenses(
            ["ui/app/page.tsx", "ui/components/Board.tsx", "ui/package.json"]
        )
        self.assertEqual(lenses, ["frontend"])

    def test_database_paths_select_dba(self):
        for path in (
            "solomon_harness/tools/database_client.py",
            "db/migrations/0001-init.surql",
        ):
            self.assertEqual(review_roster.select_lenses([path]), ["dba"], path)

    def test_ci_and_deploy_paths_select_sre(self):
        for path in (
            ".github/workflows/ci.yml",
            "docker-compose.yml",
            "scripts/git-hooks/pre-commit",
            "Dockerfile",
            "deploy/Dockerfile.worker",
        ):
            self.assertEqual(review_roster.select_lenses([path]), ["sre"], path)

    def test_loop_mechanics_select_loop_engineer(self):
        for path in (
            "solomon_harness/loop_lock.py",
            "solomon_harness/workflows.py",
        ):
            self.assertEqual(review_roster.select_lenses([path]), ["loop_engineer"], path)

    def test_loop_log_is_owned_by_loop_engineer_not_observability(self):
        # The run-log is loop mechanics (ADR-0010 territory); the loop_ prefix
        # must win over the instrumentation rule.
        self.assertEqual(
            review_roster.select_lenses(["solomon_harness/loop_log.py"]),
            ["loop_engineer"],
        )

    def test_credential_paths_select_auth_engineer(self):
        self.assertEqual(
            review_roster.select_lenses(["solomon_harness/token_store.py"]),
            ["auth_engineer"],
        )

    def test_instrumentation_selects_observability(self):
        self.assertEqual(
            review_roster.select_lenses(["solomon_harness/healthcheck.py"]),
            ["observability"],
        )

    def test_skill_content_selects_practice_curator(self):
        for path in ("agents/qa/skills/sast.md", "agents/dba/persona.md"):
            self.assertEqual(
                review_roster.select_lenses([path]), ["practice_curator"], path
            )

    def test_docs_select_documenter(self):
        for path in ("docs/solomon-workflow.md", "docs/adr/0017-review.md"):
            self.assertEqual(
                review_roster.select_lenses([path]), ["documenter"], path
            )

    def test_core_and_test_paths_select_nothing(self):
        self.assertEqual(
            review_roster.select_lenses(
                ["solomon_harness/cli.py", "tests/test_cli.py", "README.md"]
            ),
            [],
        )

    def test_cap_keeps_the_two_highest_priority_lenses(self):
        lenses = review_roster.select_lenses(
            [
                "docs/solomon-workflow.md",
                ".github/workflows/release.yml",
                "solomon_harness/tools/database_client.py",
                "solomon_harness/auth_broker.py",
            ]
        )
        self.assertEqual(lenses, ["auth_engineer", "dba"])

    def test_full_priority_chain_is_pinned_when_uncapped(self):
        # Guards against silent _RULES reordering: one path per rule, cap lifted.
        lenses = review_roster.select_lenses(_ALL_DOMAIN_PATHS, cap=len(_ALL_DOMAIN_PATHS))
        self.assertEqual(
            lenses,
            [
                "auth_engineer",
                "dba",
                "sre",
                "loop_engineer",
                "frontend",
                "observability",
                "practice_curator",
                "documenter",
            ],
        )

    def test_cap_zero_selects_nothing(self):
        self.assertEqual(review_roster.select_lenses(_ALL_DOMAIN_PATHS, cap=0), [])

    def test_many_files_of_one_domain_dedupe(self):
        lenses = review_roster.select_lenses(
            ["ui/a.tsx", "ui/b.tsx", "ui/c.css", "ui/lib/util.ts"]
        )
        self.assertEqual(lenses, ["frontend"])

    def test_mandatory_lenses_are_never_returned(self):
        # The mandatory gates run unconditionally in the command; the selector
        # only ever adds domain lenses (enforced in select_lenses, not just by
        # the current table contents).
        lenses = review_roster.select_lenses(_ALL_DOMAIN_PATHS, cap=99)
        for lens in review_roster.MANDATORY_LENSES:
            self.assertNotIn(lens, lenses)


class TestRosterMatchFitness(unittest.TestCase):
    def test_every_lens_is_a_deployable_agent(self):
        # ADR-0019 roster-match rule: a lens name with no agent definition
        # would break the Task-tool delegation at runtime on every clone.
        for _matches, lens in review_roster._RULES:
            profile = _REPO_ROOT / "agents" / lens / "agents" / f"{lens}.md"
            self.assertTrue(
                profile.is_file(),
                f"lens '{lens}' has no deployable agent at {profile}",
            )


class TestCli(unittest.TestCase):
    def test_paths_as_argv_print_one_lens_per_line(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = review_roster.main(["ui/app/page.tsx", "docs/x.md"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().splitlines(), ["frontend", "documenter"])

    def test_paths_from_stdin_when_no_argv(self):
        buf = io.StringIO()
        stdin = io.StringIO(".github/workflows/ci.yml\ndocs/x.md\n")
        with patch("sys.stdout", buf), patch("sys.stdin", stdin):
            rc = review_roster.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().splitlines(), ["sre", "documenter"])

    def test_no_match_prints_nothing_and_exits_zero(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = review_roster.main(["solomon_harness/cli.py"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
