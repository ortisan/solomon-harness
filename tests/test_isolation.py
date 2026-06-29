"""Regression tests for the hermetic-test-suite / worktree-isolation bug (#24).

These assert the two isolation guarantees that were broken: git tenant resolution
must ignore leaked GIT_* env (so the suite passes inside a worktree/hook), and the
SQLite memory path must be overridable so tests never touch the real project DB.
"""

import os
import subprocess
import tempfile
import unittest

from solomon_harness import home
from solomon_harness.tools.database_client import DatabaseClient


def _git(args, cwd):
    """Run a git command with GIT_* cleared, so it targets ``cwd``'s repo."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=env)


class TestGitEnvIsolation(unittest.TestCase):
    def test_derive_tenant_ignores_leaked_git_env(self):
        """derive_tenant resolves the target repo even when GIT_DIR/GIT_WORK_TREE
        leak from an enclosing worktree or hook."""
        with tempfile.TemporaryDirectory() as tmp:
            _git(["init"], tmp)
            _git(["remote", "add", "origin", "git@github.com:acme/widget.git"], tmp)
            saved = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE")}
            os.environ["GIT_DIR"] = os.path.join(os.getcwd(), ".git")
            os.environ["GIT_WORK_TREE"] = os.getcwd()
            try:
                self.assertEqual(home.derive_tenant(tmp), "acme-widget")
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


class TestDbPathIsolation(unittest.TestCase):
    def test_database_client_honors_harness_db_path_env(self):
        """With db_path=None, DatabaseClient writes to HARNESS_DB_PATH when set,
        never to the real project memory directory."""
        with tempfile.TemporaryDirectory() as tmp:
            dbfile = os.path.join(tmp, "long_term", "iso.db")
            saved = os.environ.get("HARNESS_DB_PATH")
            os.environ["HARNESS_DB_PATH"] = dbfile
            try:
                with DatabaseClient(harness_dir=tmp) as db:
                    db.save_memory("iso-key", "iso-value", "test")
                self.assertTrue(os.path.isfile(dbfile))
            finally:
                if saved is None:
                    os.environ.pop("HARNESS_DB_PATH", None)
                else:
                    os.environ["HARNESS_DB_PATH"] = saved


if __name__ == "__main__":
    unittest.main()
