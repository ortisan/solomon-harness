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
from solomon_harness.tools.database_client import (  # noqa: E402
    DatabaseClient,
    is_terminal,
    recover_parent,
)


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestRecoverParent(unittest.TestCase):
    """recover_parent maps a tracking row's id/title to its parent GitHub number.

    id-first (the slug's leading int before the first hyphen), else the first
    ``#<digits>`` in the title (which subsumes the ``PR #45`` form), else None.
    Pure and total: it never raises and never guesses a number that is not there.
    """

    def test_recover_parent_truth_table(self):
        cases = [
            (("68-R-01", "RAID R-01 (#68)"), "68"),   # id wins
            (("45-M2", "loop review minor"), "45"),    # id wins, no title ref
            (("R-01", "RAID R-01 (#68)"), "68"),       # id has no leading int -> title
            (("follow-up", "loop (review minor, PR #45)"), "45"),  # PR # form via #(\d+)
            (("R-07", "no number here"), None),        # nothing recoverable
            ((None, None), None),                       # total over None inputs
        ]
        for (github_id, title), expected in cases:
            with self.subTest(github_id=github_id, title=title):
                self.assertEqual(recover_parent(github_id, title), expected)


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


class TestReconcileTrackingRows(unittest.TestCase):
    """The tracking-row close pass: a slug row whose parent number is RESOLVED
    becomes terminal; every other row (open parent, absent parent, numeric) is
    spared. Never deletes a row; never touches a numeric (real GitHub) row."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed(self):
        client = DatabaseClient(db_path=self.db_path)
        # Parent #68 is resolved -> this row must close.
        client.log_issue("68-R-01", "RAID R-01 (#68)", "raid", "in_progress", None)
        # Parent #100 is present but unresolved (open) -> untouched.
        client.log_issue("100-R-02", "RAID for open issue (#100)", "raid", "in_progress", None)
        # Parent #45 is absent from the map entirely -> untouched (safe default).
        client.log_issue("45-M2", "loop review minor", "followup", "in_progress", None)
        # A real numeric GitHub row -> never a candidate.
        client.log_issue("100", "Still open numeric", "feature", "in_progress", None)
        return client

    def test_closes_resolved_parent_and_spares_the_rest(self):
        client = self._seed()
        resolved_map = {"68": True, "100": False}

        result = cli.reconcile_tracking_rows(client, resolved_map)

        self.assertEqual(result["closed"], 1)
        self.assertEqual(result["skipped_no_parent"], 0)
        self.assertEqual(result["scanned_tracking"], 3)

        # The resolved-parent row is now terminal, with its other fields preserved.
        closed_row = client.get_issue("68-R-01")
        self.assertTrue(is_terminal(closed_row["status"]))
        self.assertEqual(closed_row["title"], "RAID R-01 (#68)")
        self.assertEqual(closed_row["type_"], "raid")

        open_ids = {i["github_id"] for i in client.get_open_issues()}
        # The closed row dropped out; the open-parent, absent-parent and numeric
        # rows are all still open.
        self.assertNotIn("68-R-01", open_ids)
        self.assertEqual(open_ids, {"100-R-02", "45-M2", "100"})
        self.assertEqual(client.get_issue("100-R-02")["status"], "in_progress")
        self.assertEqual(client.get_issue("45-M2")["status"], "in_progress")
        self.assertEqual(client.get_issue("100")["status"], "in_progress")
        client.close()

    def test_skips_and_logs_row_with_no_parent(self):
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("R-07", "RAID with no number", "raid", "in_progress", None)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = cli.reconcile_tracking_rows(client, {})
        self.assertEqual(result["skipped_no_parent"], 1)
        self.assertEqual(result["closed"], 0)
        # Left open, never guessed; the unparseable slug is named on stderr.
        self.assertEqual(client.get_issue("R-07")["status"], "in_progress")
        self.assertIn("R-07", err.getvalue())
        client.close()

    def test_dry_run_collects_slugs_without_writing(self):
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("68-R-01", "RAID R-01 (#68)", "raid", "in_progress", None)

        result = cli.reconcile_tracking_rows(client, {"68": True}, dry_run=True)

        self.assertEqual(result["would_close"], ["68-R-01"])
        self.assertEqual(result["closed"], 0)
        # Nothing written on a dry run: the row is still non-terminal and open.
        self.assertEqual(client.get_issue("68-R-01")["status"], "in_progress")
        self.assertIn("68-R-01", {i["github_id"] for i in client.get_open_issues()})
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

    def test_gh_not_found_raises_runtime_error(self):
        """A missing gh binary surfaces as RuntimeError, so the caller reports it
        rather than silently repairing nothing."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(RuntimeError):
                cli._fetch_gh_issue_states(".")

    def test_malformed_json_raises_runtime_error(self):
        """Non-JSON gh output is a parse failure, not an empty result set."""
        with patch("subprocess.run", return_value=_Proc(0, "not json {")):
            with self.assertRaises(RuntimeError):
                cli._fetch_gh_issue_states(".")

    def test_non_dict_array_element_is_skipped(self):
        """A non-dict element in the gh array is treated as data and skipped, not
        trusted or coerced (STRIDE)."""
        payload = json.dumps([{"number": 6, "state": "CLOSED"}, "garbage", 42, None])
        with patch("subprocess.run", return_value=_Proc(0, payload)):
            states = cli._fetch_gh_issue_states(".")
        self.assertEqual(states, [{"number": "6", "state": "CLOSED"}])

    def test_warns_when_gh_returns_the_issue_cap(self):
        """When gh returns exactly the --limit cap, reconcile may miss closed issues
        beyond it, so the truncation is surfaced on stderr instead of hidden."""
        payload = json.dumps([{"number": 1, "state": "OPEN"}, {"number": 2, "state": "CLOSED"}])
        err = io.StringIO()
        with (
            patch.object(cli, "_GH_ISSUE_LIMIT", 2),
            patch("subprocess.run", return_value=_Proc(0, payload)),
            contextlib.redirect_stderr(err),
        ):
            states = cli._fetch_gh_issue_states(".")
        self.assertIn("cap", err.getvalue())
        self.assertEqual(len(states), 2)


class TestFetchGhPrStates(unittest.TestCase):
    """The PR-state fetch mirrors the issue fetch but accepts the extra MERGED
    literal: a parent PR counts as resolved when MERGED or CLOSED (#127)."""

    def test_fetches_pr_list_and_validates_states_as_data(self):
        payload = json.dumps(
            [
                {"number": 45, "state": "MERGED"},
                {"number": 50, "state": "CLOSED"},
                {"number": 60, "state": "OPEN"},
                {"number": "nope", "state": "MERGED"},  # bad number -> skipped
                {"number": 7, "state": "DRAFT"},        # not a state literal -> skipped
                {"state": "MERGED"},                     # missing number -> skipped
            ]
        )
        with patch("subprocess.run", return_value=_Proc(0, payload)) as run:
            states = cli._fetch_gh_pr_states(".")
        # The bulk PR listing is fetched with `gh pr list`, not a per-row call.
        self.assertEqual(run.call_args.args[0][:3], ["gh", "pr", "list"])
        self.assertEqual(
            states,
            [
                {"number": "45", "state": "MERGED"},
                {"number": "50", "state": "CLOSED"},
                {"number": "60", "state": "OPEN"},
            ],
        )

    def test_gh_failure_raises(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            with self.assertRaises(RuntimeError):
                cli._fetch_gh_pr_states(".")


class TestBuildResolvedMap(unittest.TestCase):
    """A number is RESOLVED when its issue is CLOSED or its PR is MERGED/CLOSED;
    an OPEN issue or OPEN PR records the number as not-yet-resolved (#127)."""

    def test_merges_issue_closed_or_pr_merged_or_closed(self):
        issue_states = [
            {"number": "68", "state": "CLOSED"},  # resolved via closed issue
            {"number": "100", "state": "OPEN"},   # open issue -> not resolved
        ]
        pr_states = [
            {"number": "45", "state": "MERGED"},  # resolved via merged PR
            {"number": "50", "state": "CLOSED"},  # resolved via closed PR
            {"number": "60", "state": "OPEN"},    # open PR -> not resolved
        ]
        resolved = cli._build_resolved_map(issue_states, pr_states)
        self.assertTrue(resolved["68"])
        self.assertTrue(resolved["45"])
        self.assertTrue(resolved["50"])
        self.assertFalse(resolved["100"])
        self.assertFalse(resolved["60"])
        # A number absent from both lists is not a key (treated as unresolved).
        self.assertNotIn("999", resolved)

    def test_pr_resolution_does_not_get_overridden_by_an_open_signal(self):
        # Order-independent OR: a resolved PR signal wins even if an OPEN signal
        # for the same number is seen first.
        resolved = cli._build_resolved_map(
            [{"number": "45", "state": "OPEN"}],
            [{"number": "45", "state": "MERGED"}],
        )
        self.assertTrue(resolved["45"])


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


class _ShareStoreProxy:
    """Report the shared-store backend so handle_reconcile's guard proceeds, while
    persisting to a real SQLite temp DB.

    The backend guard skips on a SQLite fallback (ADR-0006 RAID R1), which would
    otherwise stop the success path from ever running under test. This proxy lets
    the whole command path execute end to end against a real store, with no live
    SurrealDB, by delegating every read and write to the inner real client.
    """

    backend = "surrealdb"

    def __init__(self, inner):
        self._inner = inner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_issue(self, github_id):
        return self._inner.get_issue(github_id)

    def log_issue(self, *args, **kwargs):
        return self._inner.log_issue(*args, **kwargs)

    def get_open_issues(self):
        return self._inner.get_open_issues()


class TestHandleReconcileEndToEnd(unittest.TestCase):
    """The reconcile command path against a real store with a mocked gh subprocess."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")
        self.inner = DatabaseClient(db_path=self.db_path)
        self.inner.log_issue("6", "Stale closed", "bug", "in_progress", None)
        self.inner.log_issue("100", "Still open", "feature", "in_progress", None)
        self.proxy = _ShareStoreProxy(self.inner)

    def tearDown(self):
        self.inner.close()
        self.temp_dir.cleanup()

    def _gh_payload(self):
        return json.dumps(
            [{"number": 6, "state": "CLOSED"}, {"number": 100, "state": "OPEN"}]
        )

    def test_main_dispatch_dry_run_reports_without_writing(self):
        """cli.main(["reconcile", "--dry-run", ...]) dispatches to the command, which
        reports the would-repair ids and writes nothing."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out),
        ):
            cli.main(harness_dir=self.temp_dir.name, argv=["reconcile", "--dry-run"])
        self.assertIn("would be set to closed", out.getvalue())
        self.assertIn("#6", out.getvalue())
        # Nothing written on a dry run.
        self.assertEqual(self.inner.get_issue("6")["status"], "in_progress")

    def test_real_run_repairs_then_second_run_reports_zero(self):
        """A real run sets the GitHub-CLOSED row to closed and leaves the open row
        untouched; an immediate second run repairs nothing (idempotent)."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertIn("1 issue(s) set to closed", out.getvalue())
        self.assertEqual(self.inner.get_issue("6")["status"], "closed")
        self.assertEqual(self.inner.get_issue("100")["status"], "in_progress")

        out2 = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out2),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertIn("0 issue(s) set to closed", out2.getvalue())

    def test_gh_failure_exits_nonzero(self):
        """A gh failure on the (non-SQLite) success path exits non-zero and reports."""
        err = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("subprocess.run", return_value=_Proc(1, "", "gh boom")),
            contextlib.redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("reconcile failed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
