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

from solomon_harness.bootstrap import _ensure_project_gitignore
from solomon_harness.subprocess_env import clean_git_env


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, env=clean_git_env()
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

        self.assertIn("PLAN.md", self._tracked_lines())
        self.assertIn(".solomon/", self._tracked_lines())
        # untracked from git, but the working file is left in place
        self.assertFalse(_is_tracked(self.root, "PLAN.md"))
        self.assertTrue(os.path.exists(os.path.join(self.root, "PLAN.md")))

    def test_idempotent(self):
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("target/\n")
        _ensure_project_gitignore(self.root)
        _ensure_project_gitignore(self.root)
        self.assertEqual(self._tracked_lines().count("PLAN.md"), 1)
        self.assertEqual(self._tracked_lines().count(".solomon/"), 1)

    def test_creates_gitignore_when_absent(self):
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))
        _ensure_project_gitignore(self.root)
        lines = self._tracked_lines()
        self.assertIn("PLAN.md", lines)
        self.assertIn(".solomon/", lines)

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
        self.assertEqual(lines.count("PLAN.md"), 1)


if __name__ == "__main__":
    unittest.main()
