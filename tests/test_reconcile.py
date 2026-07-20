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
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness import cli  # noqa: E402
from solomon_harness.loop_lock import LoopLock, resolve_lock_path  # noqa: E402
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
            (("issue-48-d1-weak-name-validation", "d1: weak name validation"), "48"),  # issue-<n>-<slug>
            (("issue-48-d2-missing-existence-check", ""), "48"),  # issue-<n>-<slug>, no title ref
            (("issueX-5-foo", "no number here"), None),  # not the issue- prefix -> no false positive
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

    @staticmethod
    def _noop_status_fn(number, status):
        """A no-op fake standing in for the real board-status-move call, so these
        memory-side tests never shell out to gh (#264)."""
        return {"ok": True}

    def test_repairs_closed_leaves_open_and_is_idempotent(self):
        client = self._seed()
        states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
            {"number": "8", "state": "CLOSED", "board_status": "Done"},
            {"number": "100", "state": "OPEN", "board_status": "In Progress"},
        ]

        first = cli.reconcile_memory(
            client, states, set_issue_status_fn=self._noop_status_fn
        )
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
        second = cli.reconcile_memory(
            client, states, set_issue_status_fn=self._noop_status_fn
        )
        self.assertEqual(second["repaired"], 0)
        client.close()

    def test_dry_run_reports_stale_rows_without_writing(self):
        client = self._seed()
        states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
            {"number": "100", "state": "OPEN", "board_status": "In Progress"},
        ]
        result = cli.reconcile_memory(
            client, states, dry_run=True, set_issue_status_fn=self._noop_status_fn
        )
        self.assertEqual(result["would_repair"], ["6"])
        self.assertEqual(result["repaired"], 0)
        # Nothing is written on a dry run.
        self.assertEqual(client.get_issue("6")["status"], "in_progress")
        client.close()

    def test_closed_issue_without_memory_row_is_skipped(self):
        client = self._seed()
        result = cli.reconcile_memory(
            client,
            [{"number": "999", "state": "CLOSED", "board_status": "Done"}],
            set_issue_status_fn=self._noop_status_fn,
        )
        self.assertEqual(result["repaired"], 0)
        self.assertIsNone(client.get_issue("999"))
        client.close()

    def test_board_card_moves_to_done_even_when_memory_already_closed(self):
        """The #280 case: a GitHub-closed issue whose memory row is already
        terminal must still get its board card moved, proving the board move is
        decoupled from whether memory needed repair."""
        client = self._seed()
        client.log_issue("280", "Already closed in memory", "bug", "closed", None)
        states = [
            {"number": "280", "state": "CLOSED", "board_status": "Code Review"}
        ]
        calls = []

        def spy_status_fn(number, status):
            calls.append((number, status))
            return {"ok": True}

        result = cli.reconcile_memory(client, states, set_issue_status_fn=spy_status_fn)

        self.assertEqual(result["repaired"], 0)
        self.assertEqual(calls, [(280, "Done")])
        self.assertEqual(result["board_moved"], 1)
        self.assertEqual(result["board_failures"], [])
        client.close()

    def test_closed_issue_missing_from_board_uses_existing_move_primitive(self):
        client = self._seed()
        calls = []

        def spy_status_fn(number, status):
            calls.append((number, status))
            return {"ok": True}

        result = cli.reconcile_memory(
            client,
            [{"number": "6", "state": "CLOSED", "board_status": None}],
            set_issue_status_fn=spy_status_fn,
        )

        self.assertEqual(calls, [(6, "Done")])
        self.assertEqual(result["board_moved"], 1)
        client.close()

    def test_closed_issue_already_done_is_a_board_no_op(self):
        """A converged canonical card must never be written again."""
        client = self._seed()
        client.log_issue("280", "Already closed", "bug", "closed", None)
        calls = []

        def spy_status_fn(number, status):
            calls.append((number, status))
            return {"ok": True}

        result = cli.reconcile_memory(
            client,
            [{"number": "280", "state": "CLOSED", "board_status": "Done"}],
            set_issue_status_fn=spy_status_fn,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["board_moved"], 0)
        self.assertEqual(result["would_move_board"], [])
        client.close()

    def test_board_move_failure_is_reported_without_losing_memory_repair(self):
        client = self._seed()
        states = [
            {"number": "6", "state": "CLOSED", "board_status": "Code Review"}
        ]

        def failing_status_fn(number, status):
            return {"ok": False, "error": "missing Status option"}

        result = cli.reconcile_memory(client, states, set_issue_status_fn=failing_status_fn)

        # The memory write already landed and is unaffected by the board failure.
        self.assertEqual(result["repaired"], 1)
        self.assertEqual(client.get_issue("6")["status"], "closed")
        self.assertEqual(result["board_moved"], 0)
        self.assertEqual(
            result["board_failures"],
            [{"issue": "6", "ok": False, "error": "missing Status option"}],
        )
        client.close()

    def test_dry_run_never_attempts_board_move(self):
        client = self._seed()
        client.log_issue("280", "Already closed in memory", "bug", "closed", None)
        states = [
            {"number": "6", "state": "CLOSED", "board_status": "Code Review"},
            {"number": "280", "state": "CLOSED", "board_status": "Done"},
            {"number": "100", "state": "OPEN", "board_status": "In Progress"},
        ]
        calls = []

        def spy_status_fn(number, status):
            calls.append((number, status))
            return {"ok": True}

        result = cli.reconcile_memory(
            client, states, dry_run=True, set_issue_status_fn=spy_status_fn
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["would_move_board"], ["6"])
        self.assertEqual(result["board_moved"], 0)
        self.assertEqual(result["board_failures"], [])
        client.close()


class _FakeClaimStore:
    def __init__(self, versions, release_results=None, fetch_error="", events=None):
        self.versions = versions
        self.release_results = release_results or {}
        self.fetch_error = fetch_error
        self.events = events
        self.fetch_version_calls = 0
        self.release_calls = []

    def fetch_versions(self):
        self.fetch_version_calls += 1
        if self.events is not None:
            self.events.append("claim snapshot")
        return {
            "ok": not self.fetch_error,
            "versions": {} if self.fetch_error else self.versions,
            "error": self.fetch_error,
        }

    def release_if_version(self, issue_number, expected_version):
        self.release_calls.append((issue_number, expected_version))
        return self.release_results.get(
            issue_number,
            {"status": "released", "error": ""},
        )


class TestReconcileClaims(unittest.TestCase):
    def test_rejects_noncanonical_issue_aliases_at_the_policy_boundary(self):
        store = _FakeClaimStore({1: "sha-1"})

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [
                {"number": True, "state": "CLOSED", "board_status": "Done"},
                {"number": "01", "state": "CLOSED", "board_status": "Done"},
            ],
        )

        self.assertEqual(store.release_calls, [])
        self.assertEqual(result["released"], 0)

    def test_uses_the_supplied_claim_snapshot_without_reading_a_newer_one(self):
        store = _FakeClaimStore({173: "newer-sha"})
        snapshot = {"ok": True, "versions": {173: "observed-sha"}, "error": ""}

        result = cli.reconcile_claims(
            store,
            snapshot,
            [{"number": "173", "state": "CLOSED", "board_status": "Done"}],
        )

        self.assertEqual(store.fetch_version_calls, 0)
        self.assertEqual(store.release_calls, [(173, "observed-sha")])
        self.assertEqual(result["released"], 1)

    def test_closed_claim_is_force_released_and_counted(self):
        store = _FakeClaimStore({173: "sha-173"})

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [{"number": "173", "state": "CLOSED", "board_status": "Done"}],
        )

        self.assertEqual(store.fetch_version_calls, 1)
        self.assertEqual(store.release_calls, [(173, "sha-173")])
        self.assertEqual(
            result,
            {
                "released": 1,
                "already_absent": 0,
                "release_failures": [],
                "release_abort_error": "",
                "deferred_releases": [],
                "would_release": [],
                "snapshot_error": "",
                "scanned": 1,
            },
        )

    def test_open_and_unclaimed_issues_are_not_released(self):
        store = _FakeClaimStore({200: "sha-200"})

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [
                {"number": "200", "state": "OPEN", "board_status": "In Progress"},
                {"number": "201", "state": "CLOSED", "board_status": "Done"},
            ],
        )

        self.assertEqual(store.fetch_version_calls, 1)
        self.assertEqual(store.release_calls, [])
        self.assertEqual(result["released"], 0)
        self.assertEqual(result["scanned"], 2)

    def test_dry_run_reports_closed_claim_without_releasing_it(self):
        store = _FakeClaimStore({173: "sha-173"})

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [{"number": "173", "state": "CLOSED", "board_status": "Done"}],
            dry_run=True,
        )

        self.assertEqual(store.fetch_version_calls, 1)
        self.assertEqual(store.release_calls, [])
        self.assertEqual(result["released"], 0)
        self.assertEqual(result["would_release"], [173])
        self.assertEqual(result["release_failures"], [])

    def test_failed_release_is_recorded_and_does_not_stop_later_claims(self):
        store = _FakeClaimStore(
            {
                173: "sha-173",
                201: "sha-201",
            },
            release_results={
                173: {"status": "changed", "error": ""},
                201: {"status": "released", "error": ""},
            },
        )

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [
                {"number": "173", "state": "CLOSED", "board_status": "Done"},
                {"number": "201", "state": "CLOSED", "board_status": "Done"},
            ],
        )

        self.assertEqual(
            store.release_calls,
            [(173, "sha-173"), (201, "sha-201")],
        )
        self.assertEqual(result["released"], 1)
        self.assertEqual(
            result["release_failures"],
            [
                {
                    "issue": 173,
                    "ok": False,
                    "status": "changed",
                    "error": "",
                }
            ],
        )

    def test_shared_origin_failure_aborts_the_pass_and_defers_later_claims(self):
        for error in (
            "claim origin unavailable",
            "claim origin returned malformed refs",
        ):
            with self.subTest(error=error):
                store = _FakeClaimStore(
                    {173: "sha-173", 201: "sha-201"},
                    release_results={
                        173: {"status": "failed", "error": error},
                        201: {"status": "released", "error": ""},
                    },
                )

                result = cli.reconcile_claims(
                    store,
                    store.fetch_versions(),
                    [
                        {
                            "number": "173",
                            "state": "CLOSED",
                            "board_status": "Done",
                        },
                        {
                            "number": "201",
                            "state": "CLOSED",
                            "board_status": "Done",
                        },
                    ],
                )

                self.assertEqual(store.release_calls, [(173, "sha-173")])
                self.assertEqual(result["release_abort_error"], error)
                self.assertEqual(result["deferred_releases"], [201])

    def test_release_budget_defers_work_before_starting_another_remote_delete(self):
        store = _FakeClaimStore(
            {173: "sha-173", 201: "sha-201"},
            release_results={173: {"status": "changed", "error": ""}},
        )
        ticks = iter([0.0, 0.0, 61.0])

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [
                {"number": "173", "state": "CLOSED", "board_status": "Done"},
                {"number": "201", "state": "CLOSED", "board_status": "Done"},
            ],
            release_budget_seconds=60.0,
            monotonic=lambda: next(ticks),
        )

        self.assertEqual(store.release_calls, [(173, "sha-173")])
        self.assertIn("budget exhausted", result["release_abort_error"])
        self.assertEqual(result["deferred_releases"], [201])

    def test_missing_ref_after_snapshot_is_counted_as_already_absent(self):
        store = _FakeClaimStore(
            {173: "sha-173"},
            release_results={173: {"status": "missing", "error": ""}},
        )

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [{"number": "173", "state": "CLOSED", "board_status": "Done"}],
        )

        self.assertEqual(result["released"], 0)
        self.assertEqual(result["already_absent"], 1)
        self.assertEqual(result["release_failures"], [])

    def test_missing_ref_does_not_stop_a_later_deterministic_release(self):
        store = _FakeClaimStore(
            {173: "sha-173", 201: "sha-201"},
            release_results={173: {"status": "missing", "error": ""}},
        )

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [
                {"number": "173", "state": "CLOSED", "board_status": "Done"},
                {"number": "201", "state": "CLOSED", "board_status": "Done"},
            ],
        )

        self.assertEqual(
            store.release_calls,
            [(173, "sha-173"), (201, "sha-201")],
        )
        self.assertEqual(result["already_absent"], 1)
        self.assertEqual(result["released"], 1)
        self.assertEqual(result["release_abort_error"], "")

    def test_snapshot_failure_is_explicit_and_never_attempts_release(self):
        store = _FakeClaimStore({}, fetch_error="claim origin unavailable")

        result = cli.reconcile_claims(
            store,
            store.fetch_versions(),
            [{"number": "173", "state": "CLOSED", "board_status": "Done"}],
        )

        self.assertEqual(store.fetch_version_calls, 1)
        self.assertEqual(store.release_calls, [])
        self.assertEqual(result["snapshot_error"], "claim origin unavailable")
        self.assertEqual(result["released"], 0)


class TestNormalizeMemoryStatuses(unittest.TestCase):
    """The one-shot status normalization pass (#173 AC3).

    log_issue has normalized on write since ADR-0006, so only rows written before
    that (or by a path that bypassed it) can still hold a display-cased or legacy
    token. This pass canonicalizes those in place. It is a deliberately narrow
    exception to ADR-0006 decision point 1, which rejected option 1c (a destructive
    bulk rewrite): it touches only the status token, read-modify-writing through
    the unchanged log_issue, so no field is lost and no contract changes
    (ADR-0033).
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed_legacy(self, rows):
        """Seed rows whose status bypasses log_issue's normalize-on-write.

        The raw sqlite UPDATE is the point: a legacy value cannot be written
        through log_issue any more, so it must be forced in to reproduce the bug.
        """
        client = DatabaseClient(db_path=self.db_path)
        for github_id, title, type_, status in rows:
            client.log_issue(github_id, title, type_, "open", None)
        conn = sqlite3.connect(self.db_path)
        for github_id, _title, _type, status in rows:
            conn.execute(
                "UPDATE issues SET status = ? WHERE github_id = ?", (status, github_id)
            )
        conn.commit()
        conn.close()
        return client

    def test_normalizes_legacy_rows_preserving_fields_and_is_idempotent(self):
        client = self._seed_legacy([
            ("102", "Display cased", "chore", "Code Review"),
            ("133", "Lower cased", "bug", "backlog"),
            ("21", "Legacy word", "feature", "review"),
            ("140", "Spaced", "bug", "In Progress"),
        ])
        # Precondition: the store really does hold the non-canonical values.
        self.assertEqual(client.get_issue("102")["status"], "Code Review")

        first = cli.normalize_memory_statuses(client)
        self.assertEqual(first["normalized"], 4)

        self.assertEqual(client.get_issue("102")["status"], "code_review")
        self.assertEqual(client.get_issue("133")["status"], "Backlog")
        self.assertEqual(client.get_issue("21")["status"], "code_review")
        self.assertEqual(client.get_issue("140")["status"], "in_progress")
        # Other fields survive the rewrite.
        self.assertEqual(client.get_issue("102")["title"], "Display cased")
        self.assertEqual(client.get_issue("102")["type_"], "chore")

        # A second run writes nothing: no non-canonical value remains (AC3).
        second = cli.normalize_memory_statuses(client)
        self.assertEqual(second["normalized"], 0)
        client.close()

    def test_already_canonical_rows_are_not_rewritten(self):
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("200", "Canonical", "feature", "in_progress", None)
        result = cli.normalize_memory_statuses(client)
        self.assertEqual(result["normalized"], 0)
        self.assertEqual(client.get_issue("200")["status"], "in_progress")
        client.close()

    def test_preserves_non_null_milestone_and_assignee(self):
        """The full-replace UPSERT must not erase ownership metadata."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue(
            "201",
            "Owned legacy row",
            "bug",
            "open",
            "milestone-7",
            assignee="gh:alice",
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE issues SET status = ? WHERE github_id = ?",
                ("Code Review", "201"),
            )

        result = cli.normalize_memory_statuses(client)

        self.assertEqual(result["normalized"], 1)
        row = client.get_issue("201")
        self.assertEqual(row["status"], "code_review")
        self.assertEqual(row["milestone_id"], "milestone-7")
        self.assertEqual(row["assignee"], "gh:alice")
        client.close()

    def test_dry_run_reports_without_writing(self):
        client = self._seed_legacy([("102", "Display cased", "chore", "Code Review")])
        result = cli.normalize_memory_statuses(client, dry_run=True)
        self.assertEqual(result["would_normalize"], ["102"])
        self.assertEqual(result["normalized"], 0)
        self.assertEqual(client.get_issue("102")["status"], "Code Review")
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

    def test_closes_issue_prefixed_tracking_row(self):
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue(
            "issue-48-d1-weak-name-validation", "d1: weak name validation",
            "followup", "in_progress", None,
        )
        result = cli.reconcile_tracking_rows(client, {"48": True})
        self.assertEqual(result["closed"], 1)
        self.assertEqual(result["skipped_no_parent"], 0)
        self.assertTrue(
            is_terminal(client.get_issue("issue-48-d1-weak-name-validation")["status"])
        )
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

    def test_close_preserves_non_null_milestone_and_assignee(self):
        """The close pass read-modify-writes the row through the 6-arg log_issue,
        carrying every non-status field forward. A row seeded with a NON-NULL
        milestone_id and assignee must come back terminal with both fields intact,
        proving the close only rewrites the status and never drops the milestone or
        owner of a resolved tracking item."""
        client = DatabaseClient(db_path=self.db_path)
        milestone_id = client.create_milestone("M1", "goals", "2026-07-01", "active")
        client.log_issue(
            "68-R-03", "RAID R-03 (#68)", "raid", "in_progress", milestone_id, "marcelo"
        )

        result = cli.reconcile_tracking_rows(client, {"68": True})

        self.assertEqual(result["closed"], 1)
        closed_row = client.get_issue("68-R-03")
        self.assertTrue(is_terminal(closed_row["status"]))
        # The non-status fields survived the close unchanged.
        self.assertEqual(closed_row["milestone_id"], str(milestone_id))
        self.assertEqual(closed_row["assignee"], "marcelo")
        # Read back through the open-issue view as well: the row is gone from it
        # (terminal), so the survival is confirmed via the direct get_issue read.
        self.assertNotIn("68-R-03", {i["github_id"] for i in client.get_open_issues()})
        client.close()


class TestFetchGhIssueStates(unittest.TestCase):
    def test_reconcile_snapshot_uses_the_exact_canonical_board_item(self):
        """A deleted duplicate project may expose another same-title item via
        issue.projectItems (#6 live); only project item-list for the canonical
        board can prove that its real card is already Done."""
        canonical_items = [
            {
                "content": {"number": 6, "type": "Issue"},
                "status": "Done",
            }
        ]
        with (
            patch.object(
                cli,
                "_fetch_gh_issue_states",
                return_value=[{"number": "6", "state": "CLOSED"}],
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=canonical_items,
            ),
        ):
            states = cli._fetch_reconcile_issue_states(".")

        self.assertEqual(
            states,
            [{"number": "6", "state": "CLOSED", "board_status": "Done"}],
        )

    def test_canonical_board_snapshot_rejects_untrusted_and_duplicate_items(self):
        self.assertEqual(cli._canonical_board_statuses({"items": []}), {})

        statuses = cli._canonical_board_statuses(
            [
                "not-an-item",
                {
                    "content": {"number": 1, "type": "PullRequest"},
                    "status": "Done",
                },
                {"content": {"number": 2, "type": "Issue"}, "status": 42},
                {
                    "content": {"number": True, "type": "Issue"},
                    "status": "Done",
                },
                {
                    "content": {"number": "invalid", "type": "Issue"},
                    "status": "Done",
                },
                {
                    "content": {"number": "06", "type": "Issue"},
                    "status": "Done",
                },
                {
                    "content": {"number": 6, "type": "Issue"},
                    "status": "Code Review",
                },
            ]
        )

        self.assertEqual(statuses, {"6": None})

    def test_reconcile_snapshot_fails_closed_when_board_read_fails(self):
        with (
            patch.object(cli, "_fetch_gh_issue_states", return_value=[]),
            patch("solomon_harness.claim.fetch_board_items", return_value=None),
            self.assertRaisesRegex(RuntimeError, "could not read canonical board items"),
        ):
            cli._fetch_reconcile_issue_states(".")

    def test_validates_number_and_state_as_data(self):
        payload = json.dumps(
            [
                {"number": 6, "state": "CLOSED"},
                {"number": 100, "state": "OPEN"},
                {"number": "101", "state": "OPEN"},
                {"number": "nope", "state": "CLOSED"},  # bad number -> skipped
                {"number": True, "state": "CLOSED"},  # bool alias -> skipped
                {"number": "01", "state": "CLOSED"},  # leading zero -> skipped
                {"number": " 1 ", "state": "CLOSED"},  # whitespace -> skipped
                {"number": 0, "state": "CLOSED"},  # non-positive -> skipped
                {"number": -1, "state": "CLOSED"},  # non-positive -> skipped
                {"number": 1.0, "state": "CLOSED"},  # float alias -> skipped
                {"number": 7, "state": "WEIRD"},  # bad state -> skipped
                {"state": "CLOSED"},  # missing number -> skipped
            ]
        )
        with patch("subprocess.run", return_value=_Proc(0, payload)):
            states = cli._fetch_gh_issue_states(".")
        self.assertEqual(
            states,
            [
                {"number": "6", "state": "CLOSED", "title": ""},
                {"number": "100", "state": "OPEN", "title": ""},
                {"number": "101", "state": "OPEN", "title": ""},
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

    def test_gh_timeout_raises_runtime_error(self):
        """The bulk read owns a real subprocess deadline, not an outer thread."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(["gh", "issue", "list"], 15),
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
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
        self.assertEqual(states, [{"number": "6", "state": "CLOSED", "title": ""}])

    def test_strips_inherited_git_env_before_shelling_out(self):
        # Leaked git context or GH_REPO (e.g. from a hook or another worktree)
        # must not be forwarded to the gh subprocess.
        payload = json.dumps([{"number": 6, "state": "CLOSED"}])
        leaked = {
            "GIT_DIR": "/tmp/leaked/.git",
            "GIT_WORK_TREE": "/tmp/leaked",
            "GH_REPO": "attacker/other",
        }
        with patch.dict(os.environ, leaked):
            with patch("subprocess.run", return_value=_Proc(0, payload)) as run:
                cli._fetch_gh_issue_states(".")
        _, kwargs = run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env, "gh subprocess must receive an explicit, scrubbed env")
        self.assertFalse(any(k.startswith("GIT_") for k in env if k != "GIT_TERMINAL_PROMPT"))
        self.assertNotIn("GH_REPO", env)

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

    def test_a_none_number_record_is_skipped_in_both_lists(self):
        """The defensive ``number is None`` guards (one per loop) drop a record
        with no number before it can key the map, so None is never a key, while a
        valid record sitting alongside it in the same list resolves normally."""
        resolved = cli._build_resolved_map(
            [{"number": None, "state": "CLOSED"}, {"number": "68", "state": "CLOSED"}],
            [{"number": None, "state": "MERGED"}, {"number": "45", "state": "MERGED"}],
        )
        # The None-number records were skipped: None is absent from the map.
        self.assertNotIn(None, resolved)
        # The valid records sharing each list still resolved correctly.
        self.assertTrue(resolved["68"])
        self.assertTrue(resolved["45"])
        self.assertEqual(set(resolved), {"68", "45"})


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
        with tempfile.TemporaryDirectory() as workspace:
            with (
                patch(
                    "solomon_harness.tools.database_client.DatabaseClient",
                    return_value=fake,
                ),
                patch.object(
                    cli,
                    "_fetch_gh_issue_states",
                    side_effect=AssertionError("gh must not run"),
                ),
                contextlib.redirect_stderr(err),
            ):
                cli.handle_reconcile(workspace, dry_run=False)
        self.assertIn("SQLite fallback", err.getvalue())
        self.assertEqual(fake.writes, [])


class TestHandleReconcileLock(unittest.TestCase):
    def test_foreign_driver_is_refused_before_database_or_github_access(self):
        with tempfile.TemporaryDirectory() as workspace:
            os.makedirs(os.path.join(workspace, ".git"))
            holder = LoopLock(
                workspace, session_id="foreign-reconcile-driver", pid=os.getpid()
            ).acquire(stage="reconcile")
            err = io.StringIO()
            try:
                with (
                    patch(
                        "solomon_harness.tools.database_client.DatabaseClient",
                        side_effect=AssertionError("database must not open"),
                    ),
                    contextlib.redirect_stderr(err),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli.handle_reconcile(workspace, dry_run=False)
            finally:
                holder.release()

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("another solomon driver", err.getvalue())


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
        claim_versions = patch(
            "solomon_harness.claim.fetch_claim_ref_versions",
            return_value={"ok": True, "versions": {}, "error": ""},
        )
        claim_versions.start()
        self.addCleanup(claim_versions.stop)

    def tearDown(self):
        self.inner.close()
        self.temp_dir.cleanup()

    def _gh_payload(self):
        return json.dumps(
            [{"number": 6, "state": "CLOSED"}, {"number": 100, "state": "OPEN"}]
        )

    @staticmethod
    def _board_items(status="Code Review"):
        return [
            {"content": {"number": 6, "type": "Issue"}, "status": status},
            {
                "content": {"number": 100, "type": "Issue"},
                "status": "In Progress",
            },
        ]

    def test_main_dispatch_dry_run_reports_without_writing(self):
        """cli.main(["reconcile", "--dry-run", ...]) dispatches to the command, which
        reports the would-repair ids and writes nothing."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(),
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
        untouched; an immediate second run repairs nothing (idempotent). The board
        move now attempted for every CLOSED entry (#264) is faked here, matching
        this file's own precedent that the gh subprocess is always mocked."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(),
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
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
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(),
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
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
        self.assertFalse(os.path.exists(resolve_lock_path(self.temp_dir.name)))

    def test_handle_reconcile_prints_board_move_summary(self):
        """The release-path handle_reconcile gains a line reporting board moves,
        additively alongside the existing repaired/tracking/normalized lines
        (#264)."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(),
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertIn("1 board card(s) moved to Done", out.getvalue())

    def test_handle_reconcile_dry_run_reports_would_move_board(self):
        """The dry-run branch reports the would-move-board count additively,
        writing nothing."""
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(),
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=True)
        self.assertIn("1 board card(s) would move to Done", out.getvalue())

    def test_dry_run_reports_claims_from_the_existing_issue_snapshot(self):
        issue_states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
            {"number": "100", "state": "OPEN", "board_status": "In Progress"},
        ]
        store = _FakeClaimStore({6: "sha-6"})
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(
                cli, "_fetch_reconcile_issue_states", return_value=issue_states
            ) as fetch_issue_states,
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=True)

        fetch_issue_states.assert_called_once_with(self.temp_dir.name)
        self.assertEqual(store.fetch_version_calls, 1)
        self.assertEqual(store.release_calls, [])
        self.assertIn("1 claim ref(s) would be released: #6", out.getvalue())

    def test_claim_ref_snapshot_precedes_the_github_issue_snapshot(self):
        events = []
        store = _FakeClaimStore({}, events=events)

        def fetch_issue_states(_workspace_root):
            events.append("github snapshot")
            return [{"number": "6", "state": "CLOSED", "board_status": "Done"}]

        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(cli, "_fetch_reconcile_issue_states", fetch_issue_states),
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=True)

        self.assertEqual(events[:2], ["claim snapshot", "github snapshot"])

    def test_live_run_reports_claim_release_failure_and_continues(self):
        issue_states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
            {"number": "8", "state": "CLOSED", "board_status": "Done"},
        ]
        store = _FakeClaimStore(
            {
                6: "sha-6",
                8: "sha-8",
            },
            release_results={
                6: {"status": "changed", "error": ""},
                8: {"status": "released", "error": ""},
            },
        )
        out = io.StringIO()
        err = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(
                cli, "_fetch_reconcile_issue_states", return_value=issue_states
            ),
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)

        self.assertEqual(store.release_calls, [(6, "sha-6"), (8, "sha-8")])
        self.assertIn("1 claim ref(s) released", out.getvalue())
        self.assertIn("claim release failed for #6 (changed)", err.getvalue())

    def test_live_run_aborts_after_origin_loss_and_exits_nonzero(self):
        issue_states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
            {"number": "8", "state": "CLOSED", "board_status": "Done"},
        ]
        store = _FakeClaimStore(
            {6: "sha-6", 8: "sha-8"},
            release_results={
                6: {"status": "failed", "error": "claim origin unavailable"},
            },
        )
        err = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(
                cli, "_fetch_reconcile_issue_states", return_value=issue_states
            ),
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit) as raised,
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(store.release_calls, [(6, "sha-6")])
        self.assertIn("release pass aborted", err.getvalue())
        self.assertIn("deferred: #8", err.getvalue())

    def test_live_run_reports_a_claim_that_disappeared_after_the_snapshot(self):
        issue_states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
        ]
        store = _FakeClaimStore(
            {6: "sha-6"},
            release_results={6: {"status": "missing", "error": ""}},
        )
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(
                cli, "_fetch_reconcile_issue_states", return_value=issue_states
            ),
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)

        self.assertIn("1 claim ref(s) already absent", out.getvalue())

    def test_claim_snapshot_failure_is_reported_and_exits_nonzero(self):
        issue_states = [
            {"number": "6", "state": "CLOSED", "board_status": "Done"},
        ]
        store = _FakeClaimStore({}, fetch_error="claim origin unavailable")
        err = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch.object(
                cli, "_fetch_reconcile_issue_states", return_value=issue_states
            ),
            patch.object(cli, "_fetch_gh_pr_states", return_value=[]),
            patch("solomon_harness.claim.GitClaimStore", return_value=store),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit) as raised,
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)

        self.assertEqual(raised.exception.code, 1)
        self.assertIn(
            "claim snapshot failed: claim origin unavailable",
            err.getvalue(),
        )

    def test_converged_board_card_is_not_written_by_command_path(self):
        self.inner.log_issue("6", "Stale closed", "bug", "closed", None)
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch(
                "solomon_harness.claim.fetch_board_items",
                return_value=self._board_items(status="Done"),
            ),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            patch("solomon_harness.github.set_issue_status") as set_status,
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)

        set_status.assert_not_called()
        self.assertIn("0 board card(s) moved to Done", out.getvalue())


class TestHandleReconcileTracking(unittest.TestCase):
    """The reconcile command's tracking-row pass, wired end to end against a real
    store with a mocked gh. The parent is a MERGED PR, so the expanded PR path is
    exercised through the real fetch + merge + close pipeline."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")
        self.inner = DatabaseClient(db_path=self.db_path)
        self.inner.log_issue("68-R-01", "RAID R-01 (#68)", "raid", "in_progress", None)
        self.proxy = _ShareStoreProxy(self.inner)
        claim_versions = patch(
            "solomon_harness.claim.fetch_claim_ref_versions",
            return_value={"ok": True, "versions": {}, "error": ""},
        )
        claim_versions.start()
        self.addCleanup(claim_versions.stop)

    def tearDown(self):
        self.inner.close()
        self.temp_dir.cleanup()

    def _gh_payload(self):
        # Parent #68 is a MERGED PR: rejected by the issue fetch (OPEN/CLOSED only),
        # accepted by the PR fetch, so the row resolves only through the PR map.
        return json.dumps([{"number": 68, "state": "MERGED"}])

    def test_real_run_closes_then_idempotent(self):
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("solomon_harness.claim.fetch_board_items", return_value=[]),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertIn("1 tracking row(s) set to done", out.getvalue())
        # The row dropped out of the open set (became terminal).
        self.assertNotIn(
            "68-R-01", {i["github_id"] for i in self.inner.get_open_issues()}
        )

        out2 = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("solomon_harness.claim.fetch_board_items", return_value=[]),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out2),
        ):
            cli.handle_reconcile(self.temp_dir.name, dry_run=False)
        self.assertIn("0 tracking row(s) set to done", out2.getvalue())

    def test_main_dry_run_reports_rows_it_would_close(self):
        out = io.StringIO()
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=self.proxy,
            ),
            patch("solomon_harness.claim.fetch_board_items", return_value=[]),
            patch("subprocess.run", return_value=_Proc(0, self._gh_payload())),
            contextlib.redirect_stdout(out),
        ):
            cli.main(harness_dir=self.temp_dir.name, argv=["reconcile", "--dry-run"])
        self.assertIn("would be set to done", out.getvalue())
        self.assertIn("68-R-01", out.getvalue())
        # Nothing written on a dry run.
        self.assertEqual(self.inner.get_issue("68-R-01")["status"], "in_progress")


class _FakeSurrealDbClient:
    """A minimal shared-store fake for the read-oriented handle_run tests."""

    backend = "surrealdb"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_open_issues(self):
        return []

    def get_issue(self, github_id):
        return None


class TestHandleRunDoesNotReconcile(unittest.TestCase):
    """SessionStart stays read-oriented; standing mutation owns another stage."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.temp_dir.name, ".git"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_handle_run_with(self, *extra_patches):
        """Run cli.handle_run against the temp workspace with the heavy
        neighbors (db client, project scan, digest, healthcheck) stubbed out,
        plus any extra patches the caller layers on top, and return stdout."""
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch(
                    "solomon_harness.tools.database_client.DatabaseClient",
                    return_value=_FakeSurrealDbClient(),
                )
            )
            stack.enter_context(patch("solomon_harness.bootstrap.scan_project_structure"))
            stack.enter_context(
                patch("solomon_harness.digest.gather_digest", return_value=["digest line"])
            )
            stack.enter_context(patch("solomon_harness.healthcheck.run_checks", return_value=[]))
            stack.enter_context(
                patch("solomon_harness.healthcheck.pending_summary", return_value=[])
            )
            for p in extra_patches:
                stack.enter_context(p)
            with contextlib.redirect_stdout(out):
                cli.handle_run(self.temp_dir.name)
        return out.getvalue()

    def test_session_start_does_not_launch_mutating_reconcile_work(self):
        """Board convergence belongs to the locked standing stage, not a daemon.

        The pin covers the whole mutating surface: the bulk gh state fetch, the
        open-issue import pass, and the board-move primitive. The session-start
        drift line reads gh open-issue numbers, but converging stays with the
        locked reconcile stage."""
        with (
            patch.object(cli, "_fetch_gh_issue_states") as fetch_spy,
            patch.object(cli, "import_missing_issues") as import_spy,
            patch("solomon_harness.github.set_issue_status") as board_spy,
        ):
            self._run_handle_run_with()
        fetch_spy.assert_not_called()
        import_spy.assert_not_called()
        board_spy.assert_not_called()

    def test_codex_session_catalog_uses_skill_invocations_only(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-123"}, clear=True):
            output = self._run_handle_run_with()

        self.assertIn("$solomon-workflow", output)
        self.assertIn("$solomon-start", output)
        self.assertNotIn("/solomon-", output)

class TestImportMissingIssues(unittest.TestCase):
    """import_missing_issues upserts a memory row for each GitHub-OPEN issue the
    memory has never seen, so the digest and the loop select from the whole real
    backlog instead of the subset that happened to be logged at creation.
    GitHub-CLOSED entries and already-tracked rows are untouched, and GitHub
    OPEN wins over a terminal board column so an open issue can never be
    imported as delivered."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")
        self.client = DatabaseClient(db_path=self.db_path)
        self.client.log_issue("100", "Already tracked", "feature", "in_progress", None)

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def test_imports_open_missing_rows_and_leaves_the_rest_alone(self):
        states = [
            {"number": "200", "state": "OPEN", "title": "feat(memory): import pass", "board_status": "Backlog"},
            {"number": "100", "state": "OPEN", "title": "Already tracked", "board_status": None},
            {"number": "6", "state": "CLOSED", "title": "Delivered", "board_status": "Done"},
        ]
        result = cli.import_missing_issues(self.client, states)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["would_import"], ["200"])
        row = self.client.get_issue("200")
        self.assertEqual(row["title"], "feat(memory): import pass")
        self.assertEqual(row["type_"], "feature")
        self.assertEqual(row["status"], "Backlog")
        self.assertIsNone(self.client.get_issue("6"))
        self.assertEqual(self.client.get_issue("100")["status"], "in_progress")

    def test_open_issue_on_a_terminal_board_column_imports_as_open(self):
        states = [
            {"number": "201", "state": "OPEN", "title": "fix: drift", "board_status": "Done"}
        ]
        cli.import_missing_issues(self.client, states)
        row = self.client.get_issue("201")
        self.assertFalse(is_terminal(row["status"]))
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["type_"], "bug")

    def test_missing_board_column_imports_as_open(self):
        states = [
            {"number": "202", "state": "OPEN", "title": "chore: tidy", "board_status": None}
        ]
        cli.import_missing_issues(self.client, states)
        self.assertEqual(self.client.get_issue("202")["status"], "open")
        self.assertEqual(self.client.get_issue("202")["type_"], "chore")

    def test_dry_run_collects_without_writing(self):
        states = [
            {"number": "203", "state": "OPEN", "title": "feat: x", "board_status": "Ready"}
        ]
        result = cli.import_missing_issues(self.client, states, dry_run=True)
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["would_import"], ["203"])
        self.assertIsNone(self.client.get_issue("203"))

    def test_untitled_issue_gets_the_canonical_placeholder(self):
        states = [{"number": "204", "state": "OPEN", "title": "", "board_status": None}]
        cli.import_missing_issues(self.client, states)
        row = self.client.get_issue("204")
        self.assertEqual(row["title"], "GitHub issue #204")
        self.assertEqual(row["type_"], "task")


class TestIssueTypeFromTitle(unittest.TestCase):
    """The imported row's type comes from the conventional title prefix; anything
    unrecognized is the neutral "task", never a guess."""

    def test_conventional_prefix_truth_table(self):
        cases = [
            ("feat(memory): x", "feature"),
            ("feat: x", "feature"),
            ("fix(github): y", "bug"),
            ("bug: y", "bug"),
            ("chore(agents): z", "chore"),
            ("test(ui): z", "test"),
            ("docs: z", "docs"),
            ("perf(memory): z", "perf"),
            ("refactor: z", "refactor"),
            ("feature request without prefix colon", "task"),
            ("Plain prose title", "task"),
            ("", "task"),
            (None, "task"),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(cli._issue_type_from_title(title), expected)


class TestFetchCarriesTitle(unittest.TestCase):
    """The issue fetch requests the title so the import pass can create a real
    row; the title is data, never interpolated. The PR fetch keeps its lean
    number/state shape."""

    def test_fetch_gh_issue_states_requests_and_carries_the_title(self):
        payload = json.dumps([{"number": 5, "state": "OPEN", "title": "feat: x"}])
        with patch("subprocess.run", return_value=_Proc(0, payload)) as mock_run:
            states = cli._fetch_gh_issue_states(".")
        argv = mock_run.call_args.args[0]
        self.assertIn("number,state,title", argv)
        self.assertEqual(states, [{"number": "5", "state": "OPEN", "title": "feat: x"}])

    def test_missing_title_field_degrades_to_empty_string(self):
        payload = json.dumps([{"number": 7, "state": "OPEN"}])
        with patch("subprocess.run", return_value=_Proc(0, payload)):
            states = cli._fetch_gh_issue_states(".")
        self.assertEqual(states[0]["title"], "")

    def test_pr_fetch_keeps_the_number_state_shape(self):
        payload = json.dumps([{"number": 45, "state": "MERGED", "title": "ignored"}])
        with patch("subprocess.run", return_value=_Proc(0, payload)) as mock_run:
            states = cli._fetch_gh_pr_states(".")
        self.assertIn("number,state", mock_run.call_args.args[0])
        self.assertEqual(states, [{"number": "45", "state": "MERGED"}])


if __name__ == "__main__":
    unittest.main()
