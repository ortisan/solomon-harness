"""Static and content tests for the legacy_modernizer specialist (issue #70).

The suite runs under ``unittest``; ``pytest`` is declared in pyproject but not
installed in the synced venv. Run this module directly with:

    uv run python -m unittest tests.test_legacy_modernizer -v

These tests assert only statically checkable facts (files, registration,
compile output, grep-able contract text); nothing here depends on host-LLM
runtime output. They map one-to-one to issue #70 acceptance criteria
AC-01.1..01.11.
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

PROFILE_REL = os.path.join(
    "agents", "legacy_modernizer", "agents", "legacy_modernizer.md"
)
PERSONA_REL = os.path.join("agents", "legacy_modernizer", "persona.md")
SKILL_REL = os.path.join(
    "agents", "legacy_modernizer", "skills", "migration_planning.md"
)
CONFIG_REL = os.path.join("agents", "legacy_modernizer", ".agent", "config.json")
MAIN_REL = os.path.join("agents", "legacy_modernizer", "main.py")
SUBAGENT_REL = os.path.join(".claude", "agents", "legacy_modernizer.md")

VALIDATOR_PATH = os.path.join(WORKSPACE, "scripts", "validate-agents.py")
DOCUMENT_SKILLS_PATH = os.path.join(WORKSPACE, "scripts", "document-skills.py")
GENERATE_INTEGRATIONS_PATH = os.path.join(
    WORKSPACE, "scripts", "generate-integrations.py"
)

# The frozen, ordered keyword list registered for this profile. Any drift in
# order or content must fail loudly, so the test pins the exact list.
FROZEN_KEYWORDS = [
    "Legacy Modernizer",
    "parsimonious",
    "delegate",
    "sequenced",
    "incremental",
    "bounded step",
    "human-gated",
    "hexagonal",
    "OpenTelemetry",
    "secure-by-default",
    "Test-Driven Development",
]


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_validator():
    return _load_module(VALIDATOR_PATH, "validate_agents_under_test")


def _read(rel_path):
    with open(os.path.join(WORKSPACE, rel_path), "r", encoding="utf-8") as f:
        return f.read()


class _RepoRootTestCase(unittest.TestCase):
    """Pins the working directory to the repo root.

    ``validate_agent_file`` resolves and echoes the path it is given, and the
    AC-01.9 message asserts the canonical relative profile path, so the relative
    paths used in assertions must resolve against the repo root regardless of
    which directory the test runner started in.
    """

    def setUp(self):
        self._old_cwd = os.getcwd()
        os.chdir(WORKSPACE)
        self.addCleanup(os.chdir, self._old_cwd)


class TestValidatorGate(_RepoRootTestCase):
    def test_no_stale_data_science_key(self):
        validator = _load_validator()
        self.assertNotIn(
            "data_science.md",
            validator.REQUIRED_KEYWORDS,
            "the stale data_science.md key must be removed; its agent directory "
            "no longer exists (absorbed into ml_engineer)",
        )

    def test_whole_tree_validator_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "scripts/validate-agents.py"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"validator did not exit 0\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn(
            "All agent profile validation checks passed successfully.",
            result.stdout,
        )


class TestStructure(unittest.TestCase):
    def test_core_files_exist(self):
        for rel in (PROFILE_REL, PERSONA_REL, SKILL_REL, CONFIG_REL, MAIN_REL):
            self.assertTrue(
                os.path.isfile(os.path.join(WORKSPACE, rel)),
                f"missing required file: {rel}",
            )

    def test_config_named(self):
        config = json.loads(_read(CONFIG_REL))
        self.assertEqual(config["agent_name"], "legacy_modernizer")


def _front_matter_keys(content):
    """Return the ordered front-matter keys of a generated subagent file."""
    lines = content.splitlines()
    assert lines and lines[0].strip() == "---", "no opening front-matter fence"
    keys = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            keys.append(line.split(":", 1)[0].strip())
    return keys


class TestCompile(unittest.TestCase):
    def test_subagent_generated(self):
        content = _read(SUBAGENT_REL)
        self.assertTrue(content.startswith("---"), "subagent must open with ---")
        self.assertIn("name: legacy_modernizer", content)
        self.assertTrue(
            any(line.startswith("description:") for line in content.splitlines()),
            "subagent must carry a description: line",
        )
        self.assertEqual(
            _front_matter_keys(content),
            ["name", "description", "model"],
            "front-matter keys must be exactly name, description, and model",
        )


class TestDiscovery(_RepoRootTestCase):
    def test_agents_list_includes_legacy_modernizer(self):
        from solomon_harness import cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(harness_dir=WORKSPACE, argv=["agents", "list"])
        out = buf.getvalue()
        self.assertIn("Available subagents:", out)
        self.assertTrue(
            any(
                line.startswith("  legacy_modernizer - ") and line.strip() != "legacy_modernizer -"
                for line in out.splitlines()
            ),
            f"missing '  legacy_modernizer - <description>' line in:\n{out}",
        )


class TestActiveSkills(unittest.TestCase):
    def test_profile_lists_planning_skill(self):
        document_skills = _load_module(DOCUMENT_SKILLS_PATH, "document_skills_under_test")
        _title, summary = document_skills.extract_metadata(
            os.path.join(WORKSPACE, SKILL_REL)
        )
        profile = _read(PROFILE_REL)
        self.assertIn("## Active Skills", profile)
        self.assertIn("skills/migration_planning.md", profile)
        self.assertTrue(summary, "the skill must yield a non-empty one-line summary")
        self.assertIn(
            summary,
            profile,
            "the Active Skills block must carry the planning skill's one-line summary",
        )


class TestProfileContract(unittest.TestCase):
    def test_profile_states_delegation_only_boundary(self):
        low = _read(PROFILE_REL).lower()
        for token in (
            "assessment",
            "sequencing",
            "delegation",
            "delegation only",
            "delegates all execution",
            "authors no source-refactor diff",
        ):
            self.assertIn(
                token, low, f"profile must state the delegation-only boundary token: {token!r}"
            )


class TestSkillContract(unittest.TestCase):
    # AC-01.5..01.8 grep tokens (case-insensitive substrings) the skill must carry.
    MUST_CONTAIN = [
        # AC-01.5: ordered roadmap, one bounded step, big-bang rejected.
        "ordered",
        "one bounded step",
        "big-bang",
        # the eight delegates, literally.
        "software_architect",
        "software_engineer",
        "security",
        "observability",
        "qa",
        "dba",
        "sre",
        "documenter",
        # one delegate per step; bounded scope, not the whole codebase.
        "one delegate",
        "bounded scope",
        "named module",
        "whole codebase",
        # dependency-/risk-first ordering and the worked example.
        "dependency",
        "risk-first",
        "covering test",
        # out-of-set owner handling.
        "held",
        "flagged",
        "never assigned",
        # the four standards (prose forms).
        "hexagonal",
        "secure-by-default",
        # AC-01.6: termination and the human gate.
        "at most one bounded step",
        "draft pr",
        "/solomon-review",
        "no merge",
        "no release",
        "human-gated",
        # AC-01.7: each step recorded as a handoff naming the delegate.
        "log_handoff",
        "delegate",
        # AC-01.8: owner-attributed exit bars.
        "parameterized queries",
        "input validation",
        "stride",
        "port",
        "adapter",
    ]
    # Tokens where the contract accepts any one of several literal forms.
    ANY_OF = [
        ("opentelemetry", "otel"),
        ("test-driven development", "tdd"),
        ("secret-removal", "secret removal"),
        ("precede", "before any architecture refactor"),
        ("red/green/refactor", "red, green, refactor"),
    ]

    def test_skill_carries_every_contract_token(self):
        low = _read(SKILL_REL).lower()
        for token in self.MUST_CONTAIN:
            self.assertIn(token, low, f"migration_planning.md missing token: {token!r}")
        for forms in self.ANY_OF:
            self.assertTrue(
                any(form in low for form in forms),
                f"migration_planning.md missing any of: {forms!r}",
            )


class TestKeywords(_RepoRootTestCase):
    def test_frozen_keyword_list_registered(self):
        validator = _load_validator()
        self.assertIn("legacy_modernizer.md", validator.REQUIRED_KEYWORDS)
        self.assertEqual(
            validator.REQUIRED_KEYWORDS["legacy_modernizer.md"],
            FROZEN_KEYWORDS,
            "the registered keyword list must equal the frozen ordered list",
        )

    def test_profile_contains_every_required_keyword(self):
        low = _read(PROFILE_REL).lower()
        for keyword in FROZEN_KEYWORDS:
            self.assertIn(
                keyword.lower(),
                low,
                f"profile is missing required keyword {keyword!r}",
            )


class TestRealProfilePasses(_RepoRootTestCase):
    def test_real_profile_passes(self):
        validator = _load_validator()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = validator.validate_agent_file(PROFILE_REL, FROZEN_KEYWORDS)
        out = buf.getvalue()
        self.assertTrue(result, f"validate_agent_file returned False:\n{out}")
        self.assertNotIn("Error:", out)


class TestFailurePaths(_RepoRootTestCase):
    def _run(self, func):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = func()
        return result, buf.getvalue()

    def _temp_file(self, content):
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_keyword_message(self):
        validator = _load_validator()
        token = "Nonexistent-Keyword-XYZ"
        result, out = self._run(
            lambda: validator.validate_agent_file(PROFILE_REL, FROZEN_KEYWORDS + [token])
        )
        self.assertFalse(result)
        self.assertIn(
            f"Error: Required keyword/phrase '{token}' not found in {PROFILE_REL}.",
            out,
        )

    def test_emoji_message(self):
        validator = _load_validator()
        char = "\U0001f600"
        path = self._temp_file(f"Plain text {char} more text\n")
        result, out = self._run(lambda: validator.validate_agent_file(path, []))
        self.assertFalse(result)
        self.assertIn(
            f"Error: Emoji or icon '{char}' found in {path}. Emojis are strictly prohibited.",
            out,
        )

    def test_cliche_message(self):
        validator = _load_validator()
        path = self._temp_file("We leverage this approach to ship faster.\n")
        result, out = self._run(lambda: validator.validate_agent_file(path, []))
        self.assertFalse(result)
        self.assertIn(f"Error: AI cliche 'leverage' found in {path}.", out)

    def test_whole_tree_failure_footer(self):
        from unittest import mock

        validator = _load_validator()
        with mock.patch.object(
            validator, "REQUIRED_KEYWORDS", {"zzz_missing.md": ["x"]}
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    validator.main()
        out = buf.getvalue()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("\nAgent profile validation failed.", out)


class TestHumanizer(unittest.TestCase):
    def test_new_files_have_no_emoji_or_cliche(self):
        validator = _load_validator()
        for rel in (
            PROFILE_REL,
            PERSONA_REL,
            SKILL_REL,
            CONFIG_REL,
            MAIN_REL,
            SUBAGENT_REL,
        ):
            content = _read(rel)
            found, char = validator.has_emoji(content)
            self.assertFalse(found, f"{rel} contains emoji {char!r}")
            low = content.lower()
            for cliche in validator.CLICHES:
                self.assertNotIn(cliche, low, f"{rel} contains AI cliche {cliche!r}")


class TestIdempotence(unittest.TestCase):
    """A fitness guard: the committed generated artifacts must equal a second
    generator pass, so a hand-edit that bypasses the generators is caught.
    Mirrors tests/test_integrations.py::TestGeminiDrift.
    """

    def test_compile_and_document_are_stable(self):
        before_subagent = _read(SUBAGENT_REL)
        before_profile = _read(PROFILE_REL)

        generate = _load_module(GENERATE_INTEGRATIONS_PATH, "gen_integrations_idem")
        document_skills = _load_module(DOCUMENT_SKILLS_PATH, "document_skills_idem")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generate.generate(WORKSPACE)
            document_skills.document_agent(
                "legacy_modernizer", os.path.join(WORKSPACE, "agents")
            )

        self.assertEqual(
            _read(SUBAGENT_REL),
            before_subagent,
            "compile is not idempotent: .claude/agents/legacy_modernizer.md drifted",
        )
        self.assertEqual(
            _read(PROFILE_REL),
            before_profile,
            "document-skills is not idempotent: the profile drifted",
        )


if __name__ == "__main__":
    unittest.main()
