"""Duplicate-helper guards (issue #163).

_today() lived in both loop_budget.py and release.py, and _clean_git_env()
lived in home.py and worktree.py beside the canonical
subprocess_env.clean_git_env. These tests pin the deduplication: the canonical
helpers exist, and the duplicate names are gone from the modules that used to
define or re-export them, so a future edit cannot quietly fork them again.
"""

import os
import sys
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from solomon_harness import home, loop_budget, release, worktree  # noqa: E402
from solomon_harness.dates import today_iso  # noqa: E402


class TestTodayDedup(unittest.TestCase):
    """One canonical local-date helper: solomon_harness.dates.today_iso."""

    def test_canonical_today_iso_is_a_local_iso_date(self):
        self.assertRegex(today_iso(), r"^\d{4}-\d{2}-\d{2}$")

    def test_module_local_duplicates_are_gone(self):
        self.assertFalse(hasattr(loop_budget, "_today"))
        self.assertFalse(hasattr(release, "_today"))


class TestCleanGitEnvDedup(unittest.TestCase):
    """One canonical git-env scrubber: subprocess_env.clean_git_env."""

    def test_module_local_duplicates_are_gone(self):
        self.assertFalse(hasattr(home, "_clean_git_env"))
        self.assertFalse(hasattr(worktree, "_clean_git_env"))


if __name__ == "__main__":
    unittest.main()
