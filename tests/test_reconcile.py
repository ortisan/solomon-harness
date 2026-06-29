"""Tests for the reconcile command (#101).

reconcile is the backstop that converges the project memory to GitHub state:
GitHub is the source of truth, so a GitHub-CLOSED issue's memory row is set to
"closed" while GitHub-open rows are left untouched. It is idempotent, targets
the shared SurrealDB only (warns and skips on a SQLite-fallback backend), and
treats the gh output strictly as data. The gh subprocess is always mocked here;
no test runs a live reconcile against a real DB.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness import cli  # noqa: E402
from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestReconcileMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed(self):
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("6", "Stale closed", "bug", "in_progress", None)
        client.log_issue("8", "Stale closed two", "feature", "code_review", None)
        client.log_issue("100", "Still open", "feature", "in_progress", None)
        return client

    def test_repairs_closed_leaves_open_and_is_idempotent(self):
        client = self._seed()
        states = [
            {"number": "6", "state": "CLOSED"},
            {"number": "8", "state": "CLOSED"},
            {"number": "100", "state": "OPEN"},
        ]

        first = cli.reconcile_memory(client, states)
        self.assertEqual(first["repaired"], 2)

        # CLOSED rows are now terminal, with their other fields preserved.
        self.assertEqual(client.get_issue("6")["status"], "closed")
        self.assertEqual(client.get_issue("6")["title"], "Stale closed")
        self.assertEqual(client.get_issue("6")["type_"], "bug")
        self.assertEqual(client.get_issue("8")["status"], "closed")
        # The GitHub-open row is untouched.
        self.assertEqual(client.get_issue("100")["status"], "in_progress")
        self.assertEqual(
            {i["github_id"] for i in client.get_open_issues()}, {"100"}
        )

        # A second run repairs nothing (idempotent).
        second = cli.reconcile_memory(client, states)
        self.assertEqual(second["repaired"], 0)
        client.close()

    def test_dry_run_reports_stale_rows_without_writing(self):
        client = self._seed()
        states = [
            {"number": "6", "state": "CLOSED"},
            {"number": "100", "state": "OPEN"},
        ]
        result = cli.reconcile_memory(client, states, dry_run=True)
        self.assertEqual(result["would_repair"], ["6"])
        self.assertEqual(result["repaired"], 0)
        # Nothing is written on a dry run.
        self.assertEqual(client.get_issue("6")["status"], "in_progress")
        client.close()

    def test_closed_issue_without_memory_row_is_skipped(self):
        client = self._seed()
        result = cli.reconcile_memory(client, [{"number": "999", "state": "CLOSED"}])
        self.assertEqual(result["repaired"], 0)
        self.assertIsNone(client.get_issue("999"))
        client.close()


class TestFetchGhIssueStates(unittest.TestCase):
    def test_validates_number_and_state_as_data(self):
        payload = json.dumps(
            [
                {"number": 6, "state": "CLOSED"},
                {"number": 100, "state": "OPEN"},
                {"number": "nope", "state": "CLOSED"},  # bad number -> skipped
                {"number": 7, "state": "WEIRD"},  # bad state -> skipped
                {"state": "CLOSED"},  # missing number -> skipped
            ]
        )
        with patch("subprocess.run", return_value=_Proc(0, payload)):
            states = cli._fetch_gh_issue_states(".")
        self.assertEqual(
            states,
            [
                {"number": "6", "state": "CLOSED"},
                {"number": "100", "state": "OPEN"},
            ],
        )

    def test_gh_failure_raises(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            with self.assertRaises(RuntimeError):
                cli._fetch_gh_issue_states(".")


class _FakeSqliteClient:
    """A fake memory client reporting the SQLite-fallback backend.

    Records any write so the guard test can prove reconcile performs zero writes
    on a SQLite-fallback backend.
    """

    backend = "sqlite"

    def __init__(self):
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_issue(self, github_id):
        return {
            "github_id": github_id,
            "title": "x",
            "type_": "bug",
            "status": "in_progress",
            "milestone_id": None,
        }

    def log_issue(self, *args, **kwargs):
        self.writes.append(args)


class TestReconcileBackendGuard(unittest.TestCase):
    def test_sqlite_fallback_warns_and_skips_with_zero_writes(self):
        fake = _FakeSqliteClient()
        err = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=fake,
            ),
            # gh must never be shelled out to on the guard path.
            patch("subprocess.run", side_effect=AssertionError("gh must not run")),
            contextlib.redirect_stderr(err),
        ):
            cli.handle_reconcile("/workspace", dry_run=False)
        self.assertIn("SQLite fallback", err.getvalue())
        self.assertEqual(fake.writes, [])


if __name__ == "__main__":
    unittest.main()
