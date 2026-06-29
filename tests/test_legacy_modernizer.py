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


if __name__ == "__main__":
    unittest.main()
