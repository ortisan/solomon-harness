"""Regression tests for the disk-enumeration gap in scripts/validate-agents.py.

``REQUIRED_KEYWORDS`` is a hand-maintained dict keyed by filename, and
``main()`` used to iterate only that dict's keys — never the ``agents/``
directory tree on disk. Any agent profile that exists on disk but has no
entry in ``REQUIRED_KEYWORDS`` (e.g. a freshly added or renamed agent) was
therefore silently never checked, and the script still exited 0.

These tests pin two things:
  1. ``main()`` must fail loudly (non-zero exit, naming the offending file)
     when a fixture agent directory on disk has no ``REQUIRED_KEYWORDS``
     entry, instead of silently skipping it.
  2. The real ``loop_engineer`` agent profile — the concrete example named in
     the bug report — must be registered with real keywords, and the
     whole-tree validator run must still exit 0 against the real repo.
"""

import importlib.util
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

VALIDATOR_PATH = os.path.join(WORKSPACE, "scripts", "validate-agents.py")


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_agents_disk_enum_under_test", VALIDATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RepoRootTestCase(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        os.chdir(WORKSPACE)
        self.addCleanup(os.chdir, self._old_cwd)


class TestDiskEnumeration(_RepoRootTestCase):
    def test_unregistered_fixture_agent_fails_main(self):
        """An agent profile that exists on disk but is absent from
        REQUIRED_KEYWORDS must fail the run, naming the file — it must not be
        silently skipped just because main() never looked at the disk.
        """
        validator = _load_validator()

        fixture_dir = os.path.join(
            WORKSPACE, "tests", "fixtures", "unregistered_agent_tree"
        )
        fixture_profile_dir = os.path.join(fixture_dir, "ghost_agent", "agents")
        os.makedirs(fixture_profile_dir, exist_ok=True)
        fixture_profile = os.path.join(fixture_profile_dir, "ghost_agent.md")
        with open(fixture_profile, "w", encoding="utf-8") as f:
            f.write("# Ghost Agent\n\nA fixture profile with no registered keywords.\n")

        def _cleanup():
            os.remove(fixture_profile)
            os.rmdir(fixture_profile_dir)
            os.rmdir(os.path.join(fixture_dir, "ghost_agent"))
            os.rmdir(fixture_dir)

        self.addCleanup(_cleanup)

        # No REQUIRED_KEYWORDS entries at all: the only failure possible is
        # the unregistered-on-disk check, isolating exactly the bug in
        # question.
        with mock.patch.object(validator, "REQUIRED_KEYWORDS", {}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    validator.main(agents_dir=fixture_dir)

        out = buf.getvalue()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("ghost_agent.md", out)
        self.assertIn("REQUIRED_KEYWORDS", out)

    def test_registered_fixture_tree_passes(self):
        """Sanity check: a fixture tree where every on-disk profile has a
        matching REQUIRED_KEYWORDS entry (and satisfies it) exits 0.
        """
        validator = _load_validator()

        fixture_dir = os.path.join(
            WORKSPACE, "tests", "fixtures", "registered_agent_tree"
        )
        fixture_profile_dir = os.path.join(fixture_dir, "known_agent", "agents")
        os.makedirs(fixture_profile_dir, exist_ok=True)
        fixture_profile = os.path.join(fixture_profile_dir, "known_agent.md")
        with open(fixture_profile, "w", encoding="utf-8") as f:
            f.write("# Known Agent\n\nCarries the required token.\n")

        def _cleanup():
            os.remove(fixture_profile)
            os.rmdir(fixture_profile_dir)
            os.rmdir(os.path.join(fixture_dir, "known_agent"))
            os.rmdir(fixture_dir)

        self.addCleanup(_cleanup)

        with mock.patch.object(
            validator, "REQUIRED_KEYWORDS", {"known_agent.md": ["required token"]}
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    validator.main(agents_dir=fixture_dir)

        self.assertEqual(ctx.exception.code, 0)


class TestLoopEngineerRegistered(_RepoRootTestCase):
    def test_loop_engineer_has_required_keywords_entry(self):
        validator = _load_validator()
        self.assertIn(
            "loop_engineer.md",
            validator.REQUIRED_KEYWORDS,
            "loop_engineer.md must be explicitly registered in REQUIRED_KEYWORDS",
        )
        keywords = validator.REQUIRED_KEYWORDS["loop_engineer.md"]
        self.assertTrue(keywords, "loop_engineer.md keywords must not be empty")

    def test_real_loop_engineer_profile_passes_validation(self):
        validator = _load_validator()
        keywords = validator.REQUIRED_KEYWORDS["loop_engineer.md"]
        filepath = os.path.join("agents", "loop_engineer", "agents", "loop_engineer.md")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = validator.validate_agent_file(filepath, keywords)
        self.assertTrue(result, f"loop_engineer.md failed validation:\n{buf.getvalue()}")

    def test_whole_tree_validator_still_exits_zero(self):
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


if __name__ == "__main__":
    unittest.main()
