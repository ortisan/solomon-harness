"""Regression tests for the hermetic-test-suite / worktree-isolation bug (#24).

These assert the two isolation guarantees that were broken: git tenant resolution
must ignore leaked GIT_* env (so the suite passes inside a worktree/hook), and the
SQLite memory path must be overridable so tests never touch the real project DB.
"""

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

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

    def test_harness_db_path_routes_to_db_path_as_abspath(self):
        """HARNESS_DB_PATH sets self.db_path (abspath) with its parent created,
        so it forces SQLite the same way an explicit db_path argument does."""
        with tempfile.TemporaryDirectory() as tmp:
            dbfile = os.path.join(tmp, "nested", "iso.db")
            saved = os.environ.get("HARNESS_DB_PATH")
            os.environ["HARNESS_DB_PATH"] = dbfile
            try:
                with DatabaseClient(harness_dir=tmp) as db:
                    self.assertEqual(db.db_path, os.path.abspath(dbfile))
                    self.assertTrue(os.path.isdir(os.path.dirname(os.path.abspath(dbfile))))
            finally:
                if saved is None:
                    os.environ.pop("HARNESS_DB_PATH", None)
                else:
                    os.environ["HARNESS_DB_PATH"] = saved

    def test_harness_db_path_forces_sqlite_even_when_surrealdb_is_reachable(self):
        """The isolation guarantee (#40): with a surrealdb provider configured AND
        the shared server reachable, HARNESS_DB_PATH must still force SQLite. The
        surrealdb branch must never be entered, so the real shared multi-tenant
        store is never touched."""
        fake_surreal = types.ModuleType("surrealdb")
        fake_surreal.Surreal = MagicMock()  # a reachable, importable SDK
        with tempfile.TemporaryDirectory() as tmp:
            # A real config so _load_config selects the surrealdb provider (and sets
            # namespace/busy-timeout) exactly like an installed project would.
            os.makedirs(os.path.join(tmp, ".agent"))
            with open(os.path.join(tmp, ".agent", "config.json"), "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "database": {
                            "provider": "surrealdb",
                            "url": "ws://localhost:8000/rpc",
                            "username": "root",
                            "password": "root",
                            "namespace": "solomon",
                        }
                    },
                    fh,
                )
            dbfile = os.path.join(tmp, "iso.db")
            saved = os.environ.get("HARNESS_DB_PATH")
            os.environ["HARNESS_DB_PATH"] = dbfile
            try:
                # _connect_surreal returning True would mark the shared server
                # reachable; the fix must skip the branch so it is never called.
                with patch.dict(sys.modules, {"surrealdb": fake_surreal}), \
                    patch.object(
                        DatabaseClient, "_connect_surreal", return_value=True
                    ) as mock_connect:
                    client = DatabaseClient(harness_dir=tmp)
                    self.assertEqual(client.backend, "sqlite")
                    self.assertEqual(client.db_path, os.path.abspath(dbfile))
                    mock_connect.assert_not_called()
            finally:
                if saved is None:
                    os.environ.pop("HARNESS_DB_PATH", None)
                else:
                    os.environ["HARNESS_DB_PATH"] = saved


if __name__ == "__main__":
    unittest.main()
