"""`_ensure_project_gitignore` propagates the per-branch planning-artifact rule.

/solomon-start writes PLAN.md at the repo root and .solomon/ working state for
the branch in flight. They are local, per-branch state -- tracking PLAN.md makes
concurrent branches rewrite and collide on it. bootstrap must ensure every
project's .gitignore excludes them, and untrack PLAN.md when a prior commit
already tracked it (the ignore rule alone does not untrack a committed file).
"""

import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from solomon_harness.bootstrap import _ensure_project_gitignore
from solomon_harness.subprocess_env import clean_git_env


def _git(cwd, *args):
    return subprocess.run(  # noqa: S603 - fixture helper receives only test-owned arguments.
        ["git", *args],  # noqa: S607 - exercise the same operator-selected Git as production.
        cwd=cwd,
        capture_output=True,
        text=True,
        env=clean_git_env(),
    )


def _is_tracked(cwd, path):
    return _git(cwd, "ls-files", "--error-unmatch", path).returncode == 0


class TestEnsureProjectGitignore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "config", "user.name", "t")

    def tearDown(self):
        self._tmp.cleanup()

    def _read_gitignore(self):
        with open(os.path.join(self.root, ".gitignore"), encoding="utf-8") as f:
            return f.read()

    def _tracked_lines(self):
        return [
            line.strip()
            for line in self._read_gitignore().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_appends_entries_and_untracks_committed_plan(self):
        # The ortisan-iam situation: a stale .gitignore and a committed PLAN.md.
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("node_modules/\ntarget/\n")
        with open(os.path.join(self.root, "PLAN.md"), "w", encoding="utf-8") as f:
            f.write("# a branch plan\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "init")
        self.assertTrue(_is_tracked(self.root, "PLAN.md"))

        _ensure_project_gitignore(self.root)

        self.assertIn("/PLAN.md", self._tracked_lines())
        self.assertIn("/.solomon/", self._tracked_lines())
        # untracked from git, but the working file is left in place
        self.assertFalse(_is_tracked(self.root, "PLAN.md"))
        self.assertTrue(os.path.exists(os.path.join(self.root, "PLAN.md")))

    def test_untracks_committed_solomon_state_without_deleting_working_files(self):
        os.makedirs(os.path.join(self.root, ".solomon"))
        state_path = os.path.join(self.root, ".solomon", "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            f.write('{"status": "active"}\n')
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "track lifecycle state")
        self.assertTrue(_is_tracked(self.root, ".solomon/state.json"))

        _ensure_project_gitignore(self.root)

        self.assertFalse(_is_tracked(self.root, ".solomon/state.json"))
        self.assertTrue(os.path.exists(state_path))

    def test_ignores_hostile_git_environment_and_mutates_only_target_repo(self):
        with open(os.path.join(self.root, "PLAN.md"), "w", encoding="utf-8") as f:
            f.write("# target plan\n")
        _git(self.root, "add", "PLAN.md")
        _git(self.root, "commit", "-m", "track target plan")

        with tempfile.TemporaryDirectory() as unrelated:
            _git(unrelated, "init")
            _git(unrelated, "config", "user.email", "t@t")
            _git(unrelated, "config", "user.name", "t")
            with open(os.path.join(unrelated, "PLAN.md"), "w", encoding="utf-8") as f:
                f.write("# unrelated plan\n")
            _git(unrelated, "add", "PLAN.md")
            _git(unrelated, "commit", "-m", "track unrelated plan")

            hostile_env = {
                "GIT_DIR": os.path.join(unrelated, ".git"),
                "GIT_WORK_TREE": unrelated,
                "GIT_INDEX_FILE": os.path.join(unrelated, ".git", "index"),
            }
            with patch.dict(os.environ, hostile_env, clear=False):
                _ensure_project_gitignore(self.root)

            self.assertFalse(_is_tracked(self.root, "PLAN.md"))
            self.assertTrue(_is_tracked(unrelated, "PLAN.md"))

    def test_raises_and_does_not_report_success_when_git_rm_fails(self):
        plan_path = os.path.join(self.root, "PLAN.md")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write("committed\n")
        _git(self.root, "add", "PLAN.md")
        _git(self.root, "commit", "-m", "track plan")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write("staged\n")
        _git(self.root, "add", "PLAN.md")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write("working tree\n")

        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "Unable to untrack local lifecycle artifacts"):
                _ensure_project_gitignore(self.root)

        self.assertTrue(_is_tracked(self.root, "PLAN.md"))
        self.assertNotIn("Untracked local lifecycle artifacts", output.getvalue())

    def test_idempotent(self):
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("target/\n")
        _ensure_project_gitignore(self.root)
        _ensure_project_gitignore(self.root)
        self.assertEqual(self._tracked_lines().count("/PLAN.md"), 1)
        self.assertEqual(self._tracked_lines().count("/.solomon/"), 1)

    def test_creates_gitignore_when_absent(self):
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))
        _ensure_project_gitignore(self.root)
        lines = self._tracked_lines()
        self.assertIn("/PLAN.md", lines)
        self.assertIn("/.solomon/", lines)
        self.assertEqual(
            _git(
                self.root,
                "check-ignore",
                "--no-index",
                "--quiet",
                "--",
                "nested/PLAN.md",
            ).returncode,
            1,
        )
        self.assertEqual(
            _git(
                self.root,
                "check-ignore",
                "--no-index",
                "--quiet",
                "--",
                "nested/.solomon/state.json",
            ).returncode,
            1,
        )

    def test_rejects_symlinked_gitignore_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as unrelated:
            outside_gitignore = os.path.join(unrelated, ".gitignore")
            original = "outside-only/\n"
            with open(outside_gitignore, "w", encoding="utf-8") as f:
                f.write(original)
            os.symlink(outside_gitignore, os.path.join(self.root, ".gitignore"))

            with self.assertRaisesRegex(
                RuntimeError, "Unable to safely open project .gitignore"
            ):
                _ensure_project_gitignore(self.root)

            with open(outside_gitignore, encoding="utf-8") as f:
                self.assertEqual(f.read(), original)

    def test_noop_when_already_present(self):
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("PLAN.md\n.solomon/\n")
        before = self._read_gitignore()
        _ensure_project_gitignore(self.root)
        self.assertEqual(before, self._read_gitignore())

    def test_appends_only_missing_entry(self):
        # .solomon/ already present, PLAN.md missing -> only PLAN.md is added.
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write(".solomon/\n")
        _ensure_project_gitignore(self.root)
        lines = self._tracked_lines()
        self.assertEqual(lines.count(".solomon/"), 1)
        self.assertEqual(lines.count("/PLAN.md"), 1)

    def test_appends_rules_after_negations_so_git_effectively_ignores_artifacts(self):
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("PLAN.md\n.solomon/\n!PLAN.md\n!.solomon/\n")

        _ensure_project_gitignore(self.root)
        repaired = self._read_gitignore()
        _ensure_project_gitignore(self.root)

        self.assertEqual(
            _git(self.root, "check-ignore", "--no-index", "--quiet", "--", "PLAN.md").returncode,
            0,
        )
        self.assertEqual(
            _git(
                self.root,
                "check-ignore",
                "--no-index",
                "--quiet",
                "--",
                ".solomon/state.json",
            ).returncode,
            0,
        )
        self.assertEqual(self._read_gitignore(), repaired)


if __name__ == "__main__":
    unittest.main()
