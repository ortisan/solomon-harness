import contextlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# Ensure the repository root is on sys.path so the package imports cleanly.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness import cockpit_read  # noqa: E402
from solomon_harness.tools.database_client import (  # noqa: E402
    DatabaseClient,
    person_key_or_unassigned,
)

# Capture the read-path spans in memory. The global tracer provider can only be
# set once per process, so this module owns it (no other test module sets one).
_SPAN_EXPORTER = InMemorySpanExporter()


def setUpModule():
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_SPAN_EXPORTER))
    trace.set_tracer_provider(provider)

SEVEN_COLUMNS = [
    "Ideas",
    "Backlog",
    "Ready",
    "In Progress",
    "Code Review",
    "QA",
    "Done",
]

# Every write method on the read port. The read path must never call one.
WRITE_METHODS = frozenset(
    {
        "log_issue",
        "save_memory",
        "log_decision",
        "create_milestone",
        "save_release",
        "save_session",
        "log_handoff",
        "save_backtest",
        "delete_memory",
    }
)


class ReadOnlyGuard:
    """Wrap a DatabaseClient, delegate reads, and raise on any write call.

    Used to prove the cockpit read path touches only read-port methods: any
    attempt to invoke a write method records the call and raises immediately.
    """

    def __init__(self, target):
        self._target = target
        self.write_calls = []

    def __getattr__(self, name):
        if name in WRITE_METHODS:
            def _blocked(*args, **kwargs):
                self.write_calls.append(name)
                raise AssertionError(f"read path attempted a write: {name}")

            return _blocked
        return getattr(self._target, name)


class TestBuildBoard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_board_groups_into_seven_columns_with_total(self):
        """build_board groups a tenant's issues into the seven ordered columns
        with per-column counts and a reconciling total."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("b1", "Backlog one", "feature", "Backlog", None)
        client.log_issue("b2", "Backlog two", "bug", "Backlog", None)
        client.log_issue("p1", "Active one", "feature", "In Progress", None)
        client.log_issue("p2", "Active two", "feature", "In Progress", None)
        client.log_issue("p3", "Active three", "feature", "In Progress", None)

        board = cockpit_read.build_board(client, "alpha")
        client.close()

        self.assertEqual([c["name"] for c in board["columns"]], SEVEN_COLUMNS)
        counts = {c["name"]: c["count"] for c in board["columns"]}
        self.assertEqual(counts["Backlog"], 2)
        self.assertEqual(counts["In Progress"], 3)
        self.assertEqual(counts["Ideas"], 0)
        self.assertEqual(counts["Ready"], 0)
        self.assertEqual(counts["Code Review"], 0)
        self.assertEqual(counts["QA"], 0)
        self.assertEqual(counts["Done"], 0)
        self.assertEqual(board["total"], 5)
        self.assertEqual(board["unmapped"], 0)
        self.assertEqual(board["project"], "alpha")

    def test_empty_project_renders_seven_zero_columns_and_is_not_seeded(self):
        """A zero-issue tenant renders all seven headers at count 0 with total 0,
        and building the board creates no rows (it is never seeded)."""
        client = DatabaseClient(db_path=self.db_path)

        board = cockpit_read.build_board(client, "empty")

        self.assertEqual([c["name"] for c in board["columns"]], SEVEN_COLUMNS)
        self.assertTrue(all(c["count"] == 0 for c in board["columns"]))
        self.assertEqual(board["total"], 0)
        self.assertEqual(board["unmapped"], 0)
        # Re-reading the tenant proves the build did not fabricate any issue.
        self.assertEqual(client.list_issues(), [])
        client.close()

    def test_canonical_tokens_and_legacy_values_bucket_into_columns(self):
        """Issues stored as canonical snake_case tokens (in_progress, code_review,
        qa, closed) land in the In Progress / Code Review / QA / Done columns, and
        a legacy display value (In Progress, Done) lands in the same column. The
        invariant total == sum(column counts) + unmapped still holds (RAID R3)."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("c1", "Active token", "feature", "in_progress", None)
        client.log_issue("c2", "Review token", "feature", "code_review", None)
        client.log_issue("c3", "QA token", "feature", "qa", None)
        client.log_issue("c4", "Done token", "feature", "closed", None)
        client.log_issue("c5", "Legacy active", "feature", "In Progress", None)
        client.log_issue("c6", "Legacy done", "feature", "Done", None)

        board = cockpit_read.build_board(client, "alpha")
        client.close()

        counts = {c["name"]: c["count"] for c in board["columns"]}
        self.assertEqual(counts["In Progress"], 2)  # in_progress + legacy In Progress
        self.assertEqual(counts["Code Review"], 1)
        self.assertEqual(counts["QA"], 1)
        self.assertEqual(counts["Done"], 2)  # closed + legacy Done
        self.assertEqual(board["unmapped"], 0)
        self.assertEqual(board["total"], 6)
        self.assertEqual(board["total"], sum(counts.values()) + board["unmapped"])

    def test_issue_with_status_outside_columns_counts_as_unmapped(self):
        """An issue whose status is not one of the seven columns is not coerced
        into a column; it is counted in unmapped so no issue is dropped and
        total == sum(column counts) + unmapped."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("b1", "Backlog one", "feature", "Backlog", None)
        client.log_issue("x1", "Stray status", "feature", "open", None)

        board = cockpit_read.build_board(client, "alpha")
        client.close()

        column_total = sum(c["count"] for c in board["columns"])
        self.assertEqual(column_total, 1)
        self.assertEqual(board["unmapped"], 1)
        self.assertEqual(board["total"], 2)
        self.assertEqual(board["total"], column_total + board["unmapped"])

    def test_build_board_surfaces_person_key_on_each_card(self):
        """Each card carries an explicit personKey equal to
        person_key_or_unassigned(assignee): a stored email key and a gh: handle
        pass through unchanged, a null assignee resolves to the reserved
        unassigned pseudo-key (never re-derived from email/login), and the
        source issue row is never mutated by the read."""
        issues = [
            {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
            {"github_id": "a2", "status": "Backlog", "assignee": "gh:bob"},
            {"github_id": "a3", "status": "Backlog", "assignee": None},
        ]
        source = [dict(issue) for issue in issues]

        board = cockpit_read.build_board(_IssuesOnlyClient(issues), "alpha")

        cards = {
            card["github_id"]: card
            for column in board["columns"]
            for card in column["issues"]
        }
        self.assertEqual(cards["a1"]["personKey"], "alice@example.com")
        self.assertEqual(cards["a2"]["personKey"], "gh:bob")
        self.assertEqual(cards["a3"]["personKey"], person_key_or_unassigned(None))
        self.assertEqual(cards["a3"]["personKey"], "unassigned")
        # The card is a copy: the surfaced key never leaks back onto the row.
        self.assertEqual(issues, source)
        self.assertNotIn("personKey", issues[0])


class TestDiscoverProjects(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_projects_lists_all_tenants_and_writes_nothing(self):
        """discover_projects returns every tenant the lister yields, sorted, and
        performs no write on the path."""
        def lister():
            return ["gamma", "alpha", "beta"]

        self.assertEqual(
            cockpit_read.discover_projects(lister), ["alpha", "beta", "gamma"]
        )

        # Driving discovery through a guarded real client proves it is read-only.
        client = DatabaseClient(db_path=self.db_path)
        guard = ReadOnlyGuard(client)
        discovered = cockpit_read.discover_projects(guard.list_databases)
        client.close()

        self.assertEqual(guard.write_calls, [])
        self.assertIsInstance(discovered, list)
        self.assertGreaterEqual(len(discovered), 1)


class FakeTenantClient:
    """A fake read port whose issues depend on the currently bound tenant.

    Proves the board read is keyed to the selected tenant rather than the host:
    list_issues reflects whichever tenant use_tenant last bound. Records the
    ordered call sequence so a test can assert the bind happens before the read.
    """

    def __init__(self, issues_by_tenant):
        self._issues_by_tenant = dict(issues_by_tenant)
        self._bound = None
        self.calls = []

    def list_databases(self):
        self.calls.append("list_databases")
        return list(self._issues_by_tenant.keys())

    def use_tenant(self, database):
        self.calls.append(("use_tenant", database))
        self._bound = database

    def list_issues(self):
        self.calls.append("list_issues")
        return list(self._issues_by_tenant.get(self._bound, []))

    def close(self):
        self.calls.append("close")


class _IssuesOnlyClient:
    """A minimal read port that yields a fixed issue list for one tenant.

    Used to build a real ``build_board`` result for the pure ``compose_portfolio``
    tests without standing up a SQLite store: it answers only ``list_issues``.
    """

    def __init__(self, issues):
        self._issues = issues

    def list_issues(self):
        return list(self._issues)


def _ok_result(project, issues):
    """An ``OK`` per-project portfolio outcome carrying that tenant's board."""
    board = cockpit_read.build_board(_IssuesOnlyClient(issues), project)
    return {"project": project, "status": "OK", "board": board}


class TestComposePortfolio(unittest.TestCase):
    def test_compose_portfolio_reconciles_and_isolates(self):
        """compose_portfolio builds one swimlane per project in order, each
        carrying only its own issues (no cross-tenant leak), and reconciles:
        portfolio total == sum of swimlane totals == sum of the seven portfolio
        column counts + unmapped, with aggregateStatus 200 when all OK."""
        alpha_issues = [
            {"github_id": "a1", "status": "Backlog"},
            {"github_id": "a2", "status": "Backlog"},
            {"github_id": "a3", "status": "In Progress"},
            {"github_id": "a4", "status": "QA"},
            {"github_id": "a5", "status": "Done"},
        ]
        beta_issues = [
            {"github_id": "b1", "status": "Ready"},
            {"github_id": "b2", "status": "Ready"},
            {"github_id": "b3", "status": "Code Review"},
            {"github_id": "b4", "status": "Done"},
        ]
        gamma_issues = [
            {"github_id": "g1", "status": "Ideas"},
            {"github_id": "g2", "status": "Backlog"},
            {"github_id": "g3", "status": "In Progress"},
            {"github_id": "g4", "status": "In Progress"},
            {"github_id": "g5", "status": "QA"},
            {"github_id": "g6", "status": "Done"},
        ]
        results = [
            _ok_result("alpha", alpha_issues),
            _ok_result("beta", beta_issues),
            _ok_result("gamma", gamma_issues),
        ]

        portfolio = cockpit_read.compose_portfolio(results)

        # One swimlane per project, in the given order, all OK.
        self.assertEqual(
            [s["project"] for s in portfolio["swimlanes"]],
            ["alpha", "beta", "gamma"],
        )
        self.assertTrue(all(s["status"] == "OK" for s in portfolio["swimlanes"]))
        self.assertEqual(portfolio["aggregateStatus"], 200)

        # Reconciliation: total == sum of swimlane totals == columns + unmapped.
        self.assertEqual(portfolio["total"], 15)
        self.assertEqual(
            portfolio["total"], sum(s["total"] for s in portfolio["swimlanes"])
        )
        column_total = sum(c["count"] for c in portfolio["columns"])
        self.assertEqual(
            portfolio["total"], column_total + portfolio["unmapped"]
        )
        self.assertEqual(
            [c["name"] for c in portfolio["columns"]], SEVEN_COLUMNS
        )

        # No cross-tenant leak: every issue id lives only under its own swimlane.
        ids_by_project = {}
        for swimlane in portfolio["swimlanes"]:
            ids_by_project[swimlane["project"]] = {
                issue["github_id"]
                for column in swimlane["columns"]
                for issue in column["issues"]
            }
        self.assertEqual(ids_by_project["alpha"], {"a1", "a2", "a3", "a4", "a5"})
        self.assertEqual(ids_by_project["beta"], {"b1", "b2", "b3", "b4"})
        self.assertEqual(
            ids_by_project["gamma"], {"g1", "g2", "g3", "g4", "g5", "g6"}
        )
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["beta"], set())
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["gamma"], set())
        self.assertEqual(ids_by_project["beta"] & ids_by_project["gamma"], set())


    def test_compose_portfolio_degraded_carry_status_no_rows_and_207(self):
        """A mix of OK + UNREACHABLE + FORBIDDEN yields degraded swimlanes that
        carry their status and no issue rows; the FORBIDDEN swimlane carries
        httpStatus 403; the portfolio total sums OK projects only; and the
        aggregateStatus is 207 (Multi-Status)."""
        alpha_issues = [
            {"github_id": "a1", "status": "Backlog"},
            {"github_id": "a2", "status": "In Progress"},
            {"github_id": "a3", "status": "Done"},
        ]
        results = [
            _ok_result("alpha", alpha_issues),
            {"project": "beta", "status": "UNREACHABLE", "board": None},
            {"project": "gamma", "status": "FORBIDDEN", "board": None},
        ]

        portfolio = cockpit_read.compose_portfolio(results)

        lanes = {s["project"]: s for s in portfolio["swimlanes"]}
        self.assertEqual(
            [s["project"] for s in portfolio["swimlanes"]],
            ["alpha", "beta", "gamma"],
        )

        # The degraded lanes carry their status and seven columns but no rows.
        self.assertEqual(lanes["beta"]["status"], "UNREACHABLE")
        self.assertEqual(lanes["gamma"]["status"], "FORBIDDEN")
        for project in ("beta", "gamma"):
            self.assertEqual(
                [c["name"] for c in lanes[project]["columns"]], SEVEN_COLUMNS
            )
            self.assertTrue(all(c["count"] == 0 for c in lanes[project]["columns"]))
            self.assertEqual(
                [i for c in lanes[project]["columns"] for i in c["issues"]], []
            )
            self.assertEqual(lanes[project]["total"], 0)

        # FORBIDDEN carries the per-project 403; UNREACHABLE carries no upgrade.
        self.assertEqual(lanes["gamma"]["httpStatus"], 403)
        self.assertNotIn("httpStatus", lanes["beta"])

        # The total is over OK projects only, and the aggregate is 207.
        self.assertEqual(portfolio["total"], 3)
        column_total = sum(c["count"] for c in portfolio["columns"])
        self.assertEqual(portfolio["total"], column_total + portfolio["unmapped"])
        self.assertEqual(portfolio["aggregateStatus"], 207)

    def test_compose_portfolio_raises_when_reconciliation_is_violated(self):
        """The critical reconciliation guard fires: an OK result whose board total
        does not match its column counts plus unmapped raises RuntimeError instead
        of silently composing a portfolio whose totals do not add up."""
        broken = {
            "project": "alpha",
            "status": "OK",
            "board": {
                "project": "alpha",
                "columns": [
                    {"name": name, "count": 0, "issues": []}
                    for name in SEVEN_COLUMNS
                ],
                # total claims 99 while the columns sum to 0 and unmapped is 0.
                "total": 99,
                "unmapped": 0,
            },
        }

        with self.assertRaises(RuntimeError):
            cockpit_read.compose_portfolio([broken])


def _portfolio_with_assignees():
    """Compose a three-tenant portfolio whose cards carry mixed person keys.

    alice owns 3 cards in alpha and 2 in beta and none in gamma; bob owns cards
    in every tenant; two alpha cards and one beta card are unassigned. Built
    through the real compose_portfolio so every card carries the surfaced
    personKey the filter matches on.
    """
    alpha = [
        {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
        {"github_id": "a2", "status": "In Progress", "assignee": "alice@example.com"},
        {"github_id": "a3", "status": "Done", "assignee": "alice@example.com"},
        {"github_id": "a4", "status": "Backlog", "assignee": "gh:bob"},
        {"github_id": "a5", "status": "Ready", "assignee": None},
        {"github_id": "a6", "status": "QA", "assignee": None},
    ]
    beta = [
        {"github_id": "b1", "status": "Ready", "assignee": "alice@example.com"},
        {"github_id": "b2", "status": "QA", "assignee": "alice@example.com"},
        {"github_id": "b3", "status": "Done", "assignee": "gh:bob"},
        {"github_id": "b4", "status": "Backlog", "assignee": None},
    ]
    gamma = [
        {"github_id": "g1", "status": "Backlog", "assignee": "gh:bob"},
        {"github_id": "g2", "status": "In Progress", "assignee": "gh:bob"},
    ]
    return cockpit_read.compose_portfolio(
        [
            _ok_result("alpha", alpha),
            _ok_result("beta", beta),
            _ok_result("gamma", gamma),
        ]
    )


class TestFilterPortfolio(unittest.TestCase):
    def _ids_by_project(self, payload):
        return {
            lane["project"]: {
                card["github_id"]
                for column in lane["columns"]
                for card in column["issues"]
            }
            for lane in payload["swimlanes"]
        }

    def _ids_by_column(self, lane):
        return {
            column["name"]: {card["github_id"] for card in column["issues"]}
            for column in lane["columns"]
        }

    def test_filter_portfolio_narrows_to_one_person_key(self):
        """filter_portfolio keeps one swimlane per project and, within each, only
        the cards whose surfaced personKey matches: alice renders her alpha/beta
        cards with gamma a present-but-empty lane and a re-summed total of 5; a
        person assigned nowhere (carol) keeps all three lanes present and empty
        with total 0; the unassigned pseudo-key renders only the null-assignee
        cards. The lane is narrowed not flattened, filteredUser is stamped, the
        seven portfolio column counts re-sum over the matched set, and no card
        carrying another person's key survives anywhere."""
        portfolio = _portfolio_with_assignees()

        cases = {
            "alice@example.com": {
                "ids": {
                    "alpha": {"a1", "a2", "a3"},
                    "beta": {"b1", "b2"},
                    "gamma": set(),
                },
                "total": 5,
            },
            "carol@example.com": {
                "ids": {"alpha": set(), "beta": set(), "gamma": set()},
                "total": 0,
            },
            "unassigned": {
                "ids": {"alpha": {"a5", "a6"}, "beta": {"b4"}, "gamma": set()},
                "total": 3,
            },
        }

        for person_key, expected in cases.items():
            with self.subTest(person_key=person_key):
                filtered = cockpit_read.filter_portfolio(portfolio, person_key)

                # One lane per project survives: narrowed, never flattened.
                self.assertEqual(
                    [lane["project"] for lane in filtered["swimlanes"]],
                    ["alpha", "beta", "gamma"],
                )
                self.assertEqual(self._ids_by_project(filtered), expected["ids"])

                # Each lane total re-sums its filtered cards; an unmatched lane is
                # present at zero, never hidden.
                lanes = {lane["project"]: lane for lane in filtered["swimlanes"]}
                for project, ids in expected["ids"].items():
                    self.assertEqual(lanes[project]["total"], len(ids))

                # The kept cards stay in their stored columns, not just in the
                # flattened set: a regression that redistributed alice's cards
                # across columns would reconcile on the sum yet fail here.
                if person_key == "alice@example.com":
                    alpha_columns = self._ids_by_column(lanes["alpha"])
                    self.assertEqual(alpha_columns["Backlog"], {"a1"})
                    self.assertEqual(alpha_columns["In Progress"], {"a2"})
                    self.assertEqual(alpha_columns["Done"], {"a3"})
                    beta_columns = self._ids_by_column(lanes["beta"])
                    self.assertEqual(beta_columns["Ready"], {"b1"})
                    self.assertEqual(beta_columns["QA"], {"b2"})

                # The portfolio total and the seven column counts re-sum over the
                # matched set; filteredUser names the subject.
                self.assertEqual(filtered["total"], expected["total"])
                self.assertEqual(
                    sum(c["count"] for c in filtered["columns"]), expected["total"]
                )
                self.assertEqual(filtered["filteredUser"], person_key)

                # No card carrying another person's key survives in any lane.
                surviving_keys = {
                    card["personKey"]
                    for lane in filtered["swimlanes"]
                    for column in lane["columns"]
                    for card in column["issues"]
                }
                self.assertTrue(surviving_keys <= {person_key})

    def test_filter_portfolio_preserves_degraded_207_and_total_over_reachable(self):
        """Filtering a portfolio that has degraded lanes keeps each degraded
        lane's status (and the FORBIDDEN 403) untouched with no rows, holds
        aggregateStatus at 207, and sums the filtered total over the reachable
        lanes only."""
        alpha = [
            {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
            {"github_id": "a2", "status": "In Progress", "assignee": "alice@example.com"},
            {"github_id": "a3", "status": "Done", "assignee": "alice@example.com"},
            {"github_id": "a4", "status": "Backlog", "assignee": "gh:bob"},
        ]
        delta = [
            {"github_id": "d1", "status": "QA", "assignee": "alice@example.com"},
            {"github_id": "d2", "status": "Done", "assignee": "gh:bob"},
        ]
        portfolio = cockpit_read.compose_portfolio(
            [
                _ok_result("alpha", alpha),
                {"project": "beta", "status": "UNREACHABLE", "board": None},
                {"project": "gamma", "status": "FORBIDDEN", "board": None},
                _ok_result("delta", delta),
            ]
        )
        self.assertEqual(portfolio["aggregateStatus"], 207)

        filtered = cockpit_read.filter_portfolio(portfolio, "alice@example.com")

        lanes = {lane["project"]: lane for lane in filtered["swimlanes"]}
        # Lane order and presence are preserved: nothing is hidden or flattened.
        self.assertEqual(
            [lane["project"] for lane in filtered["swimlanes"]],
            ["alpha", "beta", "gamma", "delta"],
        )
        # The degraded lanes keep their status and 403, carrying no rows.
        self.assertEqual(lanes["beta"]["status"], "UNREACHABLE")
        self.assertNotIn("httpStatus", lanes["beta"])
        self.assertEqual(lanes["gamma"]["status"], "FORBIDDEN")
        self.assertEqual(lanes["gamma"]["httpStatus"], 403)
        for degraded in ("beta", "gamma"):
            self.assertEqual(lanes[degraded]["total"], 0)
            self.assertEqual(
                [card for c in lanes[degraded]["columns"] for card in c["issues"]],
                [],
            )
        # The reachable lanes render alice's filtered cards.
        self.assertEqual(lanes["alpha"]["total"], 3)
        self.assertEqual(lanes["delta"]["total"], 1)
        # 207 holds and the filtered total sums the reachable lanes only (3 + 1).
        self.assertEqual(filtered["aggregateStatus"], 207)
        self.assertEqual(filtered["total"], 4)


class _CleanTenantClient:
    """A per-tenant read port that returns a fixed issue list and closes once."""

    def __init__(self, issues):
        self._issues = issues
        self.closed = False
        self.bound = None

    def use_tenant(self, database):
        self.bound = database

    def list_issues(self):
        return list(self._issues)

    def close(self):
        self.closed = True


class _RaisingTenantClient:
    """A per-tenant read port whose ``list_issues`` raises a given error."""

    def __init__(self, error):
        self._error = error
        self.closed = False

    def use_tenant(self, database):
        pass

    def list_issues(self):
        raise self._error

    def close(self):
        self.closed = True


class _SlowTenantClient:
    """A per-tenant read port whose read blocks longer than the read timeout."""

    def __init__(self, delay):
        self._delay = delay
        self.closed = False

    def use_tenant(self, database):
        pass

    def list_issues(self):
        time.sleep(self._delay)
        return []

    def close(self):
        self.closed = True


class _CloseRecordingSlowClient:
    """A per-tenant read port whose read blocks and that records its close timing.

    Used to prove the outer read path never closes a client mid-read on timeout:
    ``list_issues`` flags itself as in-progress while it blocks, and ``close``
    records whether a read was still running when it was called. The owning worker
    must close it only after the read returns, so ``closed_during_read`` stays
    False and the outer path never triggers a close-during-read on the socket.
    """

    def __init__(self, delay):
        self._delay = delay
        self.closed = False
        self.closed_during_read = None
        self._reading = False

    def use_tenant(self, database):
        pass

    def list_issues(self):
        self._reading = True
        try:
            time.sleep(self._delay)
            return []
        finally:
            self._reading = False

    def close(self):
        self.closed_during_read = self._reading
        self.closed = True


class TestReadTenantSwimlane(unittest.TestCase):
    def test_read_tenant_swimlane_classifies_ok_forbidden_unreachable(self):
        """read_tenant_swimlane reads one tenant through its own client and
        classifies the outcome: a clean read is OK with the board; a
        PermissionError or a permission-pattern read failure is FORBIDDEN with
        no data; a read exceeding the timeout or any other failure is
        UNREACHABLE with no data."""
        # A clean read binds the tenant and returns OK with the grouped board.
        clean = _CleanTenantClient([{"github_id": "a1", "status": "Backlog"}])
        ok = cockpit_read.read_tenant_swimlane("alpha", lambda: clean, timeout=1.0)
        self.assertEqual(ok["status"], "OK")
        self.assertEqual(ok["project"], "alpha")
        self.assertEqual(ok["board"]["total"], 1)
        self.assertEqual(clean.bound, "alpha")
        self.assertTrue(clean.closed)

        # A PermissionError is FORBIDDEN and carries no board data.
        forbidden = cockpit_read.read_tenant_swimlane(
            "beta", lambda: _RaisingTenantClient(PermissionError("access denied")),
            timeout=1.0,
        )
        self.assertEqual(forbidden["status"], "FORBIDDEN")
        self.assertIsNone(forbidden["board"])

        # A permission-pattern read failure is also FORBIDDEN, no data.
        pattern = cockpit_read.read_tenant_swimlane(
            "beta",
            lambda: _RaisingTenantClient(RuntimeError("permission denied for tenant")),
            timeout=1.0,
        )
        self.assertEqual(pattern["status"], "FORBIDDEN")
        self.assertIsNone(pattern["board"])

        # A read that exceeds the timeout is UNREACHABLE, no data.
        slow = cockpit_read.read_tenant_swimlane(
            "gamma", lambda: _SlowTenantClient(0.5), timeout=0.05
        )
        self.assertEqual(slow["status"], "UNREACHABLE")
        self.assertIsNone(slow["board"])

        # A non-permission read failure (a dead connection) is UNREACHABLE.
        unreachable = cockpit_read.read_tenant_swimlane(
            "delta",
            lambda: _RaisingTenantClient(
                RuntimeError("Failed to list issues: connection lost")
            ),
            timeout=1.0,
        )
        self.assertEqual(unreachable["status"], "UNREACHABLE")
        self.assertIsNone(unreachable["board"])

    def test_read_tenant_swimlane_classifies_connect_phase_failure(self):
        """A connect-phase failure (the client_factory itself raises) is bounded
        by the per-project timeout and classified like a read failure: a generic
        connect error is UNREACHABLE, a permission-flavored connect error is
        FORBIDDEN, and neither propagates out to collapse the fan-out."""
        def refused_factory():
            raise RuntimeError("connection refused")

        refused = cockpit_read.read_tenant_swimlane(
            "alpha", refused_factory, timeout=1.0
        )
        self.assertEqual(refused["status"], "UNREACHABLE")
        self.assertIsNone(refused["board"])

        def denied_factory():
            raise RuntimeError("permission denied connecting to tenant")

        denied = cockpit_read.read_tenant_swimlane(
            "beta", denied_factory, timeout=1.0
        )
        self.assertEqual(denied["status"], "FORBIDDEN")
        self.assertIsNone(denied["board"])

    def test_read_tenant_swimlane_never_closes_a_timed_out_client_mid_read(self):
        """On timeout the outer path abandons the worker and never closes the
        client mid-read; the worker that owns the client closes it only after its
        read finally returns, so there is no close-during-read race on the socket."""
        client = _CloseRecordingSlowClient(0.5)

        result = cockpit_read.read_tenant_swimlane(
            "gamma", lambda: client, timeout=0.05
        )

        self.assertEqual(result["status"], "UNREACHABLE")
        # The worker is still reading right after the timeout; the outer path has
        # not closed the client (a mid-read close would race the live socket).
        self.assertFalse(client.closed)
        # The owning worker closes it once the read returns, never during it.
        deadline = time.time() + 2.0
        while not client.closed and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(client.closed)
        self.assertFalse(client.closed_during_read)


class TestClassifyTenantReadCancellation(unittest.TestCase):
    """_classify_tenant_read must not fire-and-forget an abandoned worker.

    ``pool.shutdown(wait=False)`` alone does not stop a worker thread that is
    still running past its reported timeout; it keeps running in the
    background, which can pile up across tenants. A cancellation-aware worker
    checks the ``threading.Event`` this function hands it and stops at its next
    checkpoint instead.
    """

    def test_classify_tenant_read_cancels_an_abandoned_worker(self):
        """On timeout, the cancel_event handed to the worker is set; a worker
        with a checkpointed loop that honors it stops within one checkpoint
        instead of running all the way to completion in the background after
        UNREACHABLE has already been reported (the fire-and-forget regression)."""
        progress = []

        def worker(cancel_event):
            for i in range(50):
                if cancel_event.is_set():
                    return "cancelled"
                progress.append(i)
                time.sleep(0.02)
            return "completed"

        status, value = cockpit_read._classify_tenant_read(worker, timeout=0.05)

        self.assertEqual(status, cockpit_read.STATUS_UNREACHABLE)
        self.assertIsNone(value)

        # The worker genuinely started (proves this isn't a crash masquerading
        # as a cancellation) before its SLA elapsed.
        progress_at_timeout = len(progress)
        self.assertGreater(progress_at_timeout, 0)

        # A fire-and-forget executor would keep the worker running for the full
        # ~1s (50 * 0.02s) regardless of the timeout already reported. Give the
        # abandoned worker one extra checkpoint's worth of time to notice the
        # cancellation and stop, then assert it actually did.
        time.sleep(0.2)
        self.assertLess(len(progress), 50)
        self.assertLessEqual(len(progress), progress_at_timeout + 2)

    def test_classify_tenant_read_still_returns_ok_on_a_clean_read(self):
        """A worker that finishes inside the timeout still returns OK with its
        value; the cancel_event plumbing does not disturb the happy path."""
        def worker(cancel_event):
            self.assertFalse(cancel_event.is_set())
            return "done"

        status, value = cockpit_read._classify_tenant_read(worker, timeout=1.0)

        self.assertEqual(status, cockpit_read.STATUS_OK)
        self.assertEqual(value, "done")


class _ConcurrencyTracker:
    """Track the peak number of per-tenant reads running at the same time."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def enter(self):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def leave(self):
        with self._lock:
            self.active -= 1


class _ConcurrentTenantClient:
    """A per-tenant read port whose read holds briefly and records concurrency.

    Shared across the fan-out via a single tracker, it proves the reads overlap
    (run in parallel) and that their peak count never exceeds the bounded pool.
    """

    def __init__(self, tenants, tracker, hold):
        self._tenants = tenants
        self._tracker = tracker
        self._hold = hold

    def list_databases(self):
        return list(self._tenants)

    def use_tenant(self, database):
        pass

    def list_issues(self):
        self._tracker.enter()
        try:
            time.sleep(self._hold)
            return []
        finally:
            self._tracker.leave()

    def close(self):
        pass


class _DiscoveryOnlyClient:
    """A read port used only for discovery: it lists the tenants and closes."""

    def __init__(self, tenants):
        self._tenants = tenants

    def list_databases(self):
        return list(self._tenants)

    def close(self):
        pass


class _ConnectFailingFactory:
    """Serves discovery on the first call, then raises on every per-tenant connect.

    ``portfolio_payload`` calls the factory once for discovery (which completes
    before the fan-out begins) and then once per tenant inside each timed worker.
    Raising on those per-tenant connects models a connection outage that strikes
    after discovery, and proves a connect-phase failure is classified within the
    worker rather than propagated out to collapse the portfolio to a 500.
    """

    def __init__(self, tenants, error):
        self._tenants = tenants
        self._error = error
        self._lock = threading.Lock()
        self._calls = 0

    def __call__(self):
        with self._lock:
            self._calls += 1
            is_discovery = self._calls == 1
        if is_discovery:
            return _DiscoveryOnlyClient(self._tenants)
        raise self._error


class TestPortfolioPayload(unittest.TestCase):
    def test_portfolio_payload_caps_at_25_with_stable_overflow(self):
        """portfolio_payload caps the fan-out at 25 swimlanes (the first 25 in
        sorted order), emits a deterministic overflow notice, excludes the same
        26th project on every load, and totals over the 25 shown."""
        names = [f"proj-{index:02d}" for index in range(26)]
        # Shuffle the discovery order so the cap is proven to run on the sorted
        # set: a cap-before-sort bug would keep a different 25 than sorted(names),
        # which a pre-sorted source would hide. A fixed seed keeps it repeatable.
        discovery_order = list(names)
        random.Random(20260629).shuffle(discovery_order)
        issues = {
            name: [{"github_id": f"{name}-1", "status": "Backlog"}]
            for name in discovery_order
        }

        def factory():
            return FakeTenantClient(issues)

        first = cockpit_read.portfolio_payload(client_factory=factory)
        second = cockpit_read.portfolio_payload(client_factory=factory)

        expected_shown = sorted(names)[:25]
        self.assertEqual(len(first["swimlanes"]), 25)
        self.assertEqual([s["project"] for s in first["swimlanes"]], expected_shown)
        self.assertEqual(first["overflow"], 1)
        self.assertEqual(first["notice"], "1 project not shown")
        self.assertEqual(first["total"], 25)
        self.assertEqual(first["aggregateStatus"], 200)

        # The excluded 26th tenant (sorted last) never appears, on either load.
        self.assertNotIn("proj-25", [s["project"] for s in first["swimlanes"]])
        self.assertEqual(
            [s["project"] for s in first["swimlanes"]],
            [s["project"] for s in second["swimlanes"]],
        )

    def test_portfolio_payload_survives_a_connect_outage(self):
        """A connection outage that makes every per-tenant connect raise is
        classified within the per-project timeout: the portfolio still composes
        (every lane UNREACHABLE with no rows, aggregateStatus 207) instead of
        propagating the connect exception out to a 500."""
        factory = _ConnectFailingFactory(
            ["alpha", "beta", "gamma"], RuntimeError("connection refused")
        )

        payload = cockpit_read.portfolio_payload(client_factory=factory, timeout=1.0)

        self.assertEqual(
            [s["project"] for s in payload["swimlanes"]], ["alpha", "beta", "gamma"]
        )
        self.assertTrue(
            all(s["status"] == "UNREACHABLE" for s in payload["swimlanes"])
        )
        self.assertTrue(all(s["total"] == 0 for s in payload["swimlanes"]))
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["aggregateStatus"], 207)

    def test_portfolio_payload_fans_out_bounded_concurrently(self):
        """portfolio_payload reads tenants in parallel (the in-flight reads
        overlap) while never exceeding the bounded worker count, so 25 reads do
        not serialize and one slow tenant cannot stall the rest."""
        names = [f"t{index:02d}" for index in range(16)]
        tracker = _ConcurrencyTracker()

        def factory():
            return _ConcurrentTenantClient(names, tracker, hold=0.05)

        payload = cockpit_read.portfolio_payload(client_factory=factory)

        self.assertEqual(len(payload["swimlanes"]), 16)
        # Reads overlap (parallel) and their peak never exceeds the worker cap.
        self.assertGreater(tracker.max_active, 1)
        self.assertLessEqual(tracker.max_active, cockpit_read.MAX_FANOUT_WORKERS)

    def test_portfolio_payload_empty_single_and_exact_cap(self):
        """portfolio_payload handles the boundaries: an empty portfolio yields no
        swimlanes (total 0, no notice, 200); a single project yields one swimlane
        whose total is the portfolio total; exactly 25 projects yields 25
        swimlanes with no overflow notice."""
        def empty_factory():
            return FakeTenantClient({})

        empty = cockpit_read.portfolio_payload(client_factory=empty_factory)
        self.assertEqual(empty["swimlanes"], [])
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["overflow"], 0)
        self.assertIsNone(empty["notice"])
        self.assertEqual(empty["aggregateStatus"], 200)

        def single_factory():
            return FakeTenantClient(
                {
                    "solo": [
                        {"github_id": "s1", "status": "Backlog"},
                        {"github_id": "s2", "status": "Done"},
                    ]
                }
            )

        single = cockpit_read.portfolio_payload(client_factory=single_factory)
        self.assertEqual([s["project"] for s in single["swimlanes"]], ["solo"])
        self.assertEqual(single["total"], 2)
        self.assertIsNone(single["notice"])
        self.assertEqual(single["aggregateStatus"], 200)

        names = [f"p{index:02d}" for index in range(25)]
        issues = {
            name: [{"github_id": f"{name}-1", "status": "Ready"}] for name in names
        }

        def exact_factory():
            return FakeTenantClient(issues)

        exact = cockpit_read.portfolio_payload(client_factory=exact_factory)
        self.assertEqual(len(exact["swimlanes"]), 25)
        self.assertEqual(exact["overflow"], 0)
        self.assertIsNone(exact["notice"])
        self.assertEqual(exact["total"], 25)

    def test_portfolio_payload_is_read_only_across_all_tenants(self):
        """Driving the whole fan-out through a ReadOnlyGuard for every tenant
        records zero write calls; because the guard raises on any write, a
        write attempt would degrade a swimlane, so the all-OK 200 result also
        proves no tenant was written."""
        issues = {
            "alpha": [
                {"github_id": "a1", "status": "Backlog"},
                {"github_id": "a2", "status": "Done"},
            ],
            "beta": [{"github_id": "b1", "status": "In Progress"}],
            "gamma": [
                {"github_id": "g1", "status": "Ready"},
                {"github_id": "g2", "status": "QA"},
                {"github_id": "g3", "status": "Done"},
            ],
        }
        guards = []

        def factory():
            guard = ReadOnlyGuard(FakeTenantClient(issues))
            guards.append(guard)
            return guard

        payload = cockpit_read.portfolio_payload(client_factory=factory)

        # A guard wrapped every client opened on the path (discovery + per-tenant).
        self.assertGreaterEqual(len(guards), 4)
        for guard in guards:
            self.assertEqual(guard.write_calls, [])
        # All OK and reconciled: no write degraded any swimlane.
        self.assertEqual(payload["aggregateStatus"], 200)
        self.assertTrue(all(s["status"] == "OK" for s in payload["swimlanes"]))
        self.assertEqual(payload["total"], 6)

    def test_portfolio_payload_no_cross_tenant_leak_through_the_fan_out(self):
        """Driving the real portfolio_payload/_fan_out with per-tenant distinct,
        identifiable ids, each swimlane carries exactly its own tenant's id set and
        the sets are pairwise disjoint. A mis-bind that returned one tenant's rows
        for every lane would fail here, where the cap test (names and counts only)
        would not, because the leak only shows in the per-row identities."""
        issues = {
            "alpha": [{"github_id": f"a{n}", "status": "Backlog"} for n in range(1, 6)],
            "beta": [{"github_id": f"b{n}", "status": "Ready"} for n in range(1, 5)],
            "gamma": [{"github_id": f"g{n}", "status": "Done"} for n in range(1, 7)],
        }

        def factory():
            return FakeTenantClient(issues)

        payload = cockpit_read.portfolio_payload(client_factory=factory)

        ids_by_project = {
            lane["project"]: {
                issue["github_id"]
                for column in lane["columns"]
                for issue in column["issues"]
            }
            for lane in payload["swimlanes"]
        }
        # Each lane carries exactly its own tenant's ids, bound per worker.
        self.assertEqual(ids_by_project["alpha"], {"a1", "a2", "a3", "a4", "a5"})
        self.assertEqual(ids_by_project["beta"], {"b1", "b2", "b3", "b4"})
        self.assertEqual(
            ids_by_project["gamma"], {"g1", "g2", "g3", "g4", "g5", "g6"}
        )
        # Pairwise disjoint: no tenant's row appears under another lane.
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["beta"], set())
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["gamma"], set())
        self.assertEqual(ids_by_project["beta"] & ids_by_project["gamma"], set())

    def test_portfolio_payload_filter_is_read_only_and_no_leak(self):
        """portfolio_payload(person=...) narrows the board to one person through
        the real fan-out: every surviving card carries that person's key, each
        lane carries only its own tenant's ids (the per-lane id sets stay
        pairwise disjoint under the filter, so nothing leaks across tenants), and
        driving every tenant through a ReadOnlyGuard records zero writes."""
        issues = {
            "alpha": [
                {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
                {"github_id": "a2", "status": "Done", "assignee": "alice@example.com"},
                {"github_id": "a3", "status": "Backlog", "assignee": "gh:bob"},
            ],
            "beta": [
                {"github_id": "b1", "status": "In Progress", "assignee": "alice@example.com"},
                {"github_id": "b2", "status": "Done", "assignee": "gh:bob"},
            ],
            "gamma": [
                {"github_id": "g1", "status": "Ready", "assignee": "alice@example.com"},
                {"github_id": "g2", "status": "QA", "assignee": "gh:bob"},
                {"github_id": "g3", "status": "Backlog", "assignee": None},
            ],
        }
        guards = []

        def factory():
            guard = ReadOnlyGuard(FakeTenantClient(issues))
            guards.append(guard)
            return guard

        payload = cockpit_read.portfolio_payload(
            client_factory=factory, person="alice@example.com"
        )

        # Only alice's cards survive, and filteredUser names the subject.
        self.assertEqual(payload["filteredUser"], "alice@example.com")
        surviving_keys = {
            card["personKey"]
            for lane in payload["swimlanes"]
            for column in lane["columns"]
            for card in column["issues"]
        }
        self.assertEqual(surviving_keys, {"alice@example.com"})

        # Each lane carries only its own tenant's filtered ids; sets are disjoint.
        ids_by_project = {
            lane["project"]: {
                card["github_id"]
                for column in lane["columns"]
                for card in column["issues"]
            }
            for lane in payload["swimlanes"]
        }
        self.assertEqual(ids_by_project["alpha"], {"a1", "a2"})
        self.assertEqual(ids_by_project["beta"], {"b1"})
        self.assertEqual(ids_by_project["gamma"], {"g1"})
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["beta"], set())
        self.assertEqual(ids_by_project["alpha"] & ids_by_project["gamma"], set())
        self.assertEqual(ids_by_project["beta"] & ids_by_project["gamma"], set())
        self.assertEqual(payload["total"], 4)

        # The filtered read path issued zero writes across every tenant.
        self.assertGreaterEqual(len(guards), 4)
        for guard in guards:
            self.assertEqual(guard.write_calls, [])
        self.assertEqual(payload["aggregateStatus"], 200)

    def test_portfolio_payload_falsy_person_is_unfiltered_no_op(self):
        """portfolio_payload no-ops on any falsy person (None or ""): both return
        today's unfiltered payload, so the seam matches the route/CLI that map a
        falsy value to no filter and no caller narrows-to-empty by accident."""
        issues = {
            "alpha": [
                {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
                {"github_id": "a2", "status": "Done", "assignee": "gh:bob"},
            ],
            "beta": [
                {"github_id": "b1", "status": "Ready", "assignee": None},
            ],
        }

        def factory():
            return FakeTenantClient(issues)

        unfiltered = cockpit_read.portfolio_payload(client_factory=factory)
        explicit_none = cockpit_read.portfolio_payload(
            client_factory=factory, person=None
        )
        empty_person = cockpit_read.portfolio_payload(
            client_factory=factory, person=""
        )

        self.assertEqual(unfiltered, explicit_none)
        # An empty person string narrows to nothing if treated as a filter; the
        # seam must no-op it instead of stamping filteredUser="" with total 0.
        self.assertEqual(unfiltered, empty_person)
        self.assertNotIn("filteredUser", empty_person)
        self.assertNotIn("filteredUser", unfiltered)
        self.assertEqual(unfiltered["total"], 3)


class TestPortfolioCli(unittest.TestCase):
    def setUp(self):
        _SPAN_EXPORTER.clear()

    def test_portfolio_cli_outputs_aggregate_json(self):
        """main(["portfolio"]) prints the aggregate portfolio JSON (swimlanes,
        total, aggregateStatus) for the Node bridge and emits the
        cockpit.portfolio span for the audit trace."""
        issues = {
            "alpha": [{"github_id": "a1", "status": "Backlog"}],
            "beta": [{"github_id": "b1", "status": "Done"}],
        }
        out = io.StringIO()
        with patch(
            "solomon_harness.cockpit_read.DatabaseClient",
            side_effect=lambda *args, **kwargs: FakeTenantClient(issues),
        ):
            with contextlib.redirect_stdout(out):
                rc = cockpit_read.main(["portfolio"])

        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertIn("swimlanes", printed)
        self.assertEqual(
            sorted(s["project"] for s in printed["swimlanes"]), ["alpha", "beta"]
        )
        self.assertEqual(printed["total"], 2)
        self.assertEqual(printed["aggregateStatus"], 200)

        span_names = [s.name for s in _SPAN_EXPORTER.get_finished_spans()]
        self.assertIn("cockpit.portfolio", span_names)

    def test_portfolio_cli_filters_by_user(self):
        """main(["portfolio", "--user", <key>]) prints the portfolio narrowed to
        that person: filteredUser names the subject and only that person's cards
        survive, so the route can bridge the filter server-side."""
        issues = {
            "alpha": [
                {"github_id": "a1", "status": "Backlog", "assignee": "alice@example.com"},
                {"github_id": "a2", "status": "Done", "assignee": "gh:bob"},
            ],
            "beta": [
                {"github_id": "b1", "status": "Ready", "assignee": "alice@example.com"},
            ],
        }
        out = io.StringIO()
        with patch(
            "solomon_harness.cockpit_read.DatabaseClient",
            side_effect=lambda *args, **kwargs: FakeTenantClient(issues),
        ):
            with contextlib.redirect_stdout(out):
                rc = cockpit_read.main(["portfolio", "--user", "alice@example.com"])

        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["filteredUser"], "alice@example.com")
        ids = {
            card["github_id"]
            for lane in printed["swimlanes"]
            for column in lane["columns"]
            for card in column["issues"]
        }
        self.assertEqual(ids, {"a1", "b1"})


class TestBoardPayloadTenantTargeting(unittest.TestCase):
    def test_board_payload_reads_selected_tenant_not_host(self):
        """board_payload binds the selected tenant before reading, so two
        distinct tenants yield distinct boards each labeled with its own
        project, not the host tenant's content."""
        fake = FakeTenantClient(
            {
                "alpha": [{"github_id": "a1", "status": "Backlog"}],
                "beta": [
                    {"github_id": "b1", "status": "In Progress"},
                    {"github_id": "b2", "status": "Done"},
                ],
            }
        )

        alpha = cockpit_read.board_payload("alpha", client_factory=lambda: fake)
        beta = cockpit_read.board_payload("beta", client_factory=lambda: fake)

        # Each board is labeled with its requested tenant and is keyed to it.
        self.assertEqual(alpha["project"], "alpha")
        self.assertEqual(beta["project"], "beta")
        self.assertTrue(alpha["found"])
        self.assertTrue(beta["found"])
        # Selecting a different tenant produces different column content.
        self.assertNotEqual(alpha["columns"], beta["columns"])
        alpha_counts = {c["name"]: c["count"] for c in alpha["columns"]}
        beta_counts = {c["name"]: c["count"] for c in beta["columns"]}
        self.assertEqual(alpha_counts["Backlog"], 1)
        self.assertEqual(beta_counts["In Progress"], 1)
        self.assertEqual(beta_counts["Done"], 1)
        # The selected tenant is bound before the issue read on each request.
        self.assertIn(("use_tenant", "alpha"), fake.calls)
        self.assertIn(("use_tenant", "beta"), fake.calls)
        self.assertLess(
            fake.calls.index(("use_tenant", "alpha")),
            fake.calls.index("list_issues"),
        )


class TestBoardPayloadRejection(unittest.TestCase):
    def _binds(self, calls):
        return [c for c in calls if isinstance(c, tuple) and c[0] == "use_tenant"]

    def test_board_payload_rejects_unknown_and_injection_without_reading(self):
        """An unknown or shell-injection project is rejected before any rebind
        or read: board_payload returns the all-zero empty board flagged
        found False, and neither use_tenant nor list_issues is called. The CLI
        prints the same found:false payload for the Node bridge."""
        for bad in ("ghost", "alpha; rm -rf ~"):
            fake = FakeTenantClient(
                {"alpha": [{"github_id": "a1", "status": "Backlog"}]}
            )
            payload = cockpit_read.board_payload(bad, client_factory=lambda: fake)

            self.assertFalse(payload["found"])
            self.assertEqual(payload["project"], bad)
            self.assertEqual(payload["total"], 0)
            self.assertEqual(
                [c["name"] for c in payload["columns"]], SEVEN_COLUMNS
            )
            self.assertTrue(all(c["count"] == 0 for c in payload["columns"]))
            # The rejected request never rebinds a tenant or reads its issues.
            self.assertEqual(self._binds(fake.calls), [])
            self.assertNotIn("list_issues", fake.calls)

        # The CLI surfaces the same rejection: found:false JSON, no read.
        fake = FakeTenantClient({"alpha": [{"github_id": "a1", "status": "Backlog"}]})
        out = io.StringIO()
        with patch("solomon_harness.cockpit_read.DatabaseClient", return_value=fake):
            with contextlib.redirect_stdout(out):
                rc = cockpit_read.main(["board", "--project", "ghost"])

        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertFalse(printed["found"])
        self.assertEqual(printed["project"], "ghost")
        self.assertEqual(self._binds(fake.calls), [])
        self.assertNotIn("list_issues", fake.calls)


class TestReadPathInstrumentation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")
        _SPAN_EXPORTER.clear()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_cli(self, *args):
        env = dict(os.environ)
        env["HARNESS_DB_PATH"] = self.db_path
        env["PYTHONPATH"] = repo_root
        return subprocess.run(
            [sys.executable, "-m", "solomon_harness.cockpit_read", *args],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_build_board_emits_read_span_and_cli_outputs_json(self):
        """build_board records a cockpit.read_board span, and the __main__ CLI
        prints valid board JSON for the Node bridge."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("b1", "Backlog one", "feature", "Backlog", None)
        cockpit_read.build_board(client, "alpha")
        client.close()

        span_names = [s.name for s in _SPAN_EXPORTER.get_finished_spans()]
        self.assertIn("cockpit.read_board", span_names)

        projects = json.loads(self._run_cli("projects").stdout)
        self.assertIsInstance(projects, list)
        self.assertGreaterEqual(len(projects), 1)

        board = json.loads(self._run_cli("board", "--project", projects[0]).stdout)
        self.assertEqual([c["name"] for c in board["columns"]], SEVEN_COLUMNS)
        self.assertEqual(board["project"], projects[0])
        self.assertTrue(board["found"])


class TestReadOnlyContract(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "harness.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_read_path_issues_only_read_operations(self):
        """A full board build and discovery, driven through a proxy that raises
        on any write, completes using read-port reads only."""
        client = DatabaseClient(db_path=self.db_path)
        client.log_issue("b1", "Backlog one", "feature", "Backlog", None)
        client.log_issue("d1", "Done one", "feature", "Done", None)
        guard = ReadOnlyGuard(client)

        board = cockpit_read.build_board(guard, "alpha")
        projects = cockpit_read.discover_projects(guard.list_databases)
        client.close()

        self.assertEqual(guard.write_calls, [])
        self.assertEqual(board["total"], 2)
        self.assertEqual(board["unmapped"], 0)
        self.assertIsInstance(projects, list)

    def test_guard_raises_on_any_write(self):
        """The guard has teeth: a write through it raises, so the read-only
        contract test above cannot be a false positive."""
        client = DatabaseClient(db_path=self.db_path)
        guard = ReadOnlyGuard(client)
        with self.assertRaises(AssertionError):
            guard.log_issue("x", "title", "feature", "Backlog", None)
        self.assertEqual(guard.write_calls, ["log_issue"])
        client.close()


# ---------------------------------------------------------------------------
# Per-user velocity (issue #55, slice 3a).
#
# Frozen clock for every velocity test: T_NOW is naive local time, matching the
# naive ISO strings record_transition writes for entered_at. The three windows
# start at T_NOW - {7, 14, 30} days.
# ---------------------------------------------------------------------------

T_NOW = datetime(2026, 6, 29, 12, 0, 0)


def _done_history(entered_at):
    """A one-entry board_history that records a Done transition at entered_at."""
    return [{"column": "Done", "entered_at": entered_at}]


class _VelocityTenantClient:
    """A per-tenant read port that answers list_issues and board_history reads.

    list_issues returns the fixed issue list; get_memory_bulk answers every
    requested board_history:<github_id> key from the supplied history map in
    one call (a key with no tracked history is simply absent from the
    result). Deliberately carries no per-key get_memory method, so a
    regression to the N+1 read pattern (one get_memory call per issue) fails
    loudly with an AttributeError rather than silently working. Records every
    batch call so a test can assert the history read costs exactly one round
    trip regardless of issue count. Read-only: no write method exists.
    """

    def __init__(self, issues, history_by_id=None):
        self._issues = issues
        self._history = dict(history_by_id or {})
        self.bulk_calls = []

    def use_tenant(self, database):
        pass

    def list_issues(self):
        return list(self._issues)

    def get_memory_bulk(self, keys):
        self.bulk_calls.append(list(keys))
        prefix = "board_history:"
        result = {}
        for key in keys:
            if not key.startswith(prefix):
                continue
            history = self._history.get(key[len(prefix):])
            if history is not None:
                result[key] = json.dumps(history)
        return result

    def close(self):
        pass


class TestCountTenantVelocity(unittest.TestCase):
    def _tenant(self):
        """One tenant whose board_history exercises every window boundary.

        alice has nine Done transitions laid out so the count is 3 / 7 / 9 over
        the 7 / 14 / 30-day windows, plus two Done-column issues with no tracked
        history (the excluded affordance). carol's single Done sits exactly on
        the 14-day lower bound (inclusive); dave's single Done is one second
        before it (excluded). bob is an assignee with no in-window Done (a
        present zero-throughput subject). Two null-assignee Done issues fall
        under the reserved unassigned bucket.
        """
        alice_done = {
            # Inside the 7-day window (>= 2026-06-22T12:00:00): three.
            "al1": "2026-06-29T10:00:00",
            "al2": "2026-06-25T09:00:00",
            "al3": "2026-06-22T12:00:00",  # exactly the 7-day lower bound
            # Inside 14 but outside 7 (>= 2026-06-15T12:00:00): four more.
            "al4": "2026-06-21T08:00:00",
            "al5": "2026-06-18T15:00:00",
            "al6": "2026-06-16T11:00:00",
            "al7": "2026-06-15T12:00:00",  # exactly the 14-day lower bound
            # Inside 30 but outside 14 (>= 2026-05-30T12:00:00): two more.
            "al8": "2026-06-10T09:00:00",
            "al9": "2026-06-01T09:00:00",
        }
        issues = [
            {"github_id": gid, "status": "closed", "assignee": "alice@example.com"}
            for gid in alice_done
        ]
        history = {gid: _done_history(ts) for gid, ts in alice_done.items()}

        # Two alice issues sit in the Done column with no tracked history: they
        # are excluded from the count and reported, never silently dropped.
        issues += [
            {"github_id": "al-x1", "status": "closed", "assignee": "alice@example.com"},
            {"github_id": "al-x2", "status": "Done", "assignee": "alice@example.com"},
        ]

        # carol: one Done exactly on the 14-day lower bound (inclusive -> 1).
        issues.append(
            {"github_id": "ca1", "status": "closed", "assignee": "carol@example.com"}
        )
        history["ca1"] = _done_history("2026-06-15T12:00:00")

        # dave: one Done one second before the 14-day bound (excluded -> 0).
        issues.append(
            {"github_id": "da1", "status": "closed", "assignee": "dave@example.com"}
        )
        history["da1"] = _done_history("2026-06-15T11:59:59")

        # bob: an assignee with no in-window Done (zero throughput, still a row).
        issues.append(
            {"github_id": "bo1", "status": "Backlog", "assignee": "gh:bob"}
        )

        # Two unassigned Done issues inside the window -> the unassigned bucket.
        issues += [
            {"github_id": "un1", "status": "closed", "assignee": None},
            {"github_id": "un2", "status": "closed", "assignee": None},
        ]
        history["un1"] = _done_history("2026-06-24T09:00:00")
        history["un2"] = _done_history("2026-06-20T09:00:00")

        return _VelocityTenantClient(issues, history)

    def test_count_tenant_velocity_counts_done_in_window_per_person(self):
        """count_tenant_velocity counts, per canonical person key, the issues
        whose board_history Done transition entered the window; the lower bound
        is inclusive and one second before it is excluded; a null assignee falls
        under the unassigned bucket; a zero-throughput assignee is still a
        present row; and Done-column issues with no tracked history are reported
        as excluded without ever entering the count."""
        counts = cockpit_read.count_tenant_velocity(
            self._tenant(), "alpha", now=T_NOW, days=14
        )

        # alice: seven Done in the 14-day window; her two history-less Done
        # issues are excluded, not counted.
        self.assertEqual(counts["alice@example.com"]["count"], 7)
        self.assertEqual(counts["alice@example.com"]["excluded"], 2)

        # The 14-day lower bound is inclusive (carol) and -1s is out (dave).
        self.assertEqual(counts["carol@example.com"]["count"], 1)
        self.assertEqual(counts["dave@example.com"]["count"], 0)

        # A null assignee buckets under the reserved unassigned key, not merged.
        self.assertEqual(counts["unassigned"]["count"], 2)

        # A zero-throughput assignee is present with count 0 (not dropped).
        self.assertIn("gh:bob", counts)
        self.assertEqual(counts["gh:bob"]["count"], 0)

    def test_count_tenant_velocity_selects_the_window(self):
        """The same fixture yields 3 / 7 / 9 for alice across the 7 / 14 / 30-day
        windows, so the window bound (now - days) drives the count."""
        for days, expected in ((7, 3), (14, 7), (30, 9)):
            with self.subTest(days=days):
                counts = cockpit_read.count_tenant_velocity(
                    self._tenant(), "alpha", now=T_NOW, days=days
                )
                self.assertEqual(counts["alice@example.com"]["count"], expected)

    def test_count_tenant_velocity_reads_board_history_in_one_batch_call(self):
        """count_tenant_velocity reads every issue's board_history through a
        single get_memory_bulk call, not one get_memory per issue (no N+1): a
        tenant with many issues still costs exactly one history round trip,
        carrying every issue's key."""
        issues = [
            {"github_id": f"m{i}", "status": "closed", "assignee": "alice@example.com"}
            for i in range(50)
        ]
        history = {
            f"m{i}": _done_history("2026-06-28T10:00:00") for i in range(50)
        }
        client = _VelocityTenantClient(issues, history)

        counts = cockpit_read.count_tenant_velocity(
            client, "alpha", now=T_NOW, days=14
        )

        self.assertEqual(len(client.bulk_calls), 1)
        self.assertEqual(
            set(client.bulk_calls[0]),
            {f"board_history:m{i}" for i in range(50)},
        )
        self.assertEqual(counts["alice@example.com"]["count"], 50)

    def test_count_tenant_velocity_stops_at_the_next_issue_when_cancelled(self):
        """A cancel_event already set before the per-issue loop starts stops
        count_tenant_velocity at the very first checkpoint: no issue is
        counted, proving the loop actually observes cancellation rather than
        running to completion regardless of it."""
        client = self._tenant()
        cancel_event = threading.Event()
        cancel_event.set()

        counts = cockpit_read.count_tenant_velocity(
            client, "alpha", now=T_NOW, days=14, cancel_event=cancel_event
        )

        self.assertEqual(counts, {})


def _ok_velocity(project, velocity):
    """An OK per-tenant velocity result carrying that tenant's per-person counts."""
    return {"project": project, "status": "OK", "velocity": velocity}


class TestComposeVelocity(unittest.TestCase):
    def test_compose_velocity_sums_per_person_across_tenants(self):
        """compose_velocity sums each person's per-tenant counts into one row:
        alice appears once reading 7 (4 alpha + 3 beta) with perTenant
        {alpha:4, beta:3}; a person's perTenant lists only the tenants where they
        delivered; aggregateStatus is 200 when every tenant is OK; and no person
        is duplicated as a separate per-tenant subject."""
        results = [
            _ok_velocity(
                "alpha",
                {
                    "alice@example.com": {
                        "count": 4,
                        "excluded": 1,
                        "doneAt": [
                            "2026-06-28T10:00:00",
                            "2026-06-27T10:00:00",
                            "2026-06-26T10:00:00",
                            "2026-06-25T10:00:00",
                        ],
                    },
                    "gh:bob": {"count": 1, "excluded": 0, "doneAt": ["2026-06-24T10:00:00"]},
                },
            ),
            _ok_velocity(
                "beta",
                {
                    "alice@example.com": {
                        "count": 3,
                        "excluded": 0,
                        "doneAt": [
                            "2026-06-23T10:00:00",
                            "2026-06-22T10:00:00",
                            "2026-06-21T10:00:00",
                        ],
                    },
                    "gh:bob": {"count": 0, "excluded": 0, "doneAt": []},
                },
            ),
        ]

        payload = cockpit_read.compose_velocity(results)

        self.assertEqual(payload["aggregateStatus"], 200)
        self.assertEqual(payload["degraded"], [])

        rows = {row["personKey"]: row for row in payload["rows"]}
        # alice once, summed across tenants, with the per-tenant breakdown.
        person_keys = [row["personKey"] for row in payload["rows"]]
        self.assertEqual(person_keys.count("alice@example.com"), 1)
        self.assertEqual(rows["alice@example.com"]["count"], 7)
        self.assertEqual(
            rows["alice@example.com"]["perTenant"], {"alpha": 4, "beta": 3}
        )
        self.assertEqual(rows["alice@example.com"]["excluded"], 1)
        # No degraded tenant, so no figure is partial.
        self.assertFalse(rows["alice@example.com"]["partial"])
        self.assertEqual(rows["alice@example.com"]["partialTenants"], [])

        # bob appears once; perTenant lists only the tenant he delivered in.
        self.assertEqual(person_keys.count("gh:bob"), 1)
        self.assertEqual(rows["gh:bob"]["count"], 1)
        self.assertEqual(rows["gh:bob"]["perTenant"], {"alpha": 1})

    def test_compose_velocity_marks_partial_and_207_when_tenant_degraded(self):
        """A degraded (UNREACHABLE) tenant lifts the aggregate to 207, contributes
        no counts, and flags every per-person figure partial naming the degraded
        tenant; the reachable tenants compute in full. Because the degraded tenant
        could have held deliveries for any person, the figure is the reachable
        subtotal, never presented as complete."""
        results = [
            _ok_velocity(
                "alpha",
                {
                    "alice@example.com": {
                        "count": 4,
                        "excluded": 0,
                        "doneAt": [
                            "2026-06-28T10:00:00",
                            "2026-06-27T10:00:00",
                            "2026-06-26T10:00:00",
                            "2026-06-25T10:00:00",
                        ],
                    }
                },
            ),
            _ok_velocity(
                "beta",
                {
                    "alice@example.com": {
                        "count": 3,
                        "excluded": 0,
                        "doneAt": [
                            "2026-06-23T10:00:00",
                            "2026-06-22T10:00:00",
                            "2026-06-21T10:00:00",
                        ],
                    }
                },
            ),
            {"project": "gamma", "status": "UNREACHABLE", "velocity": None},
        ]

        payload = cockpit_read.compose_velocity(results)

        # The degraded tenant lifts the aggregate to 207 and is named.
        self.assertEqual(payload["aggregateStatus"], 207)
        self.assertEqual(payload["degraded"], ["gamma"])

        rows = {row["personKey"]: row for row in payload["rows"]}
        alice = rows["alice@example.com"]
        # alpha and beta compute in full; gamma contributes nothing.
        self.assertEqual(alice["count"], 7)
        self.assertEqual(alice["perTenant"], {"alpha": 4, "beta": 3})
        self.assertNotIn("gamma", alice["perTenant"])
        # Every figure is flagged partial naming the degraded tenant.
        self.assertTrue(alice["partial"])
        self.assertEqual(alice["partialTenants"], ["gamma"])


class _VelocityFanoutClient:
    """A multi-tenant read port for the velocity fan-out.

    list_issues and get_memory_bulk both answer for whichever tenant use_tenant
    last bound, so a mis-bind (reading the wrong tenant's history) would surface
    as a wrong attribution. Deliberately carries no per-key get_memory method,
    so a regression to the N+1 read pattern fails loudly. Records the ordered
    call sequence so a test can assert the bind happens before the read and
    that the history read costs one batch call, not one per issue. Read-only:
    no write method exists.
    """

    def __init__(self, by_tenant):
        self._by_tenant = by_tenant
        self._bound = None
        self.calls = []

    def list_databases(self):
        self.calls.append("list_databases")
        return list(self._by_tenant.keys())

    def use_tenant(self, database):
        self.calls.append(("use_tenant", database))
        self._bound = database

    def list_issues(self):
        self.calls.append("list_issues")
        return list(self._by_tenant.get(self._bound, {}).get("issues", []))

    def get_memory_bulk(self, keys):
        self.calls.append(("get_memory_bulk", tuple(keys)))
        prefix = "board_history:"
        history_by_id = self._by_tenant.get(self._bound, {}).get("history", {})
        result = {}
        for key in keys:
            if not key.startswith(prefix):
                continue
            history = history_by_id.get(key[len(prefix):])
            if history is not None:
                result[key] = json.dumps(history)
        return result

    def close(self):
        self.calls.append("close")


def _alice_tenant(github_prefix, timestamps):
    """A tenant fixture where alice delivered once per supplied in-window date."""
    issues = [
        {"github_id": f"{github_prefix}{index}", "status": "closed", "assignee": "alice@example.com"}
        for index, _ in enumerate(timestamps)
    ]
    history = {
        f"{github_prefix}{index}": _done_history(ts)
        for index, ts in enumerate(timestamps)
    }
    return {"issues": issues, "history": history}


class TestVelocityPayload(unittest.TestCase):
    def test_velocity_payload_reads_each_tenant_in_isolation_and_writes_nothing(self):
        """velocity_payload fans out over the tenants, reading each through its
        own client bound via use_tenant before the read, composes the per-person
        counts, and issues zero writes. Driving every tenant through a
        ReadOnlyGuard records no write call; alice's figure is the per-tenant sum
        with the correct breakdown, proving the lanes are composed never joined."""
        data = {
            "alpha": _alice_tenant(
                "a",
                ["2026-06-28T10:00:00", "2026-06-27T10:00:00", "2026-06-26T10:00:00", "2026-06-25T10:00:00"],
            ),
            "beta": _alice_tenant(
                "b", ["2026-06-24T10:00:00", "2026-06-23T10:00:00", "2026-06-22T10:00:00"]
            ),
            "gamma": _alice_tenant("g", ["2026-06-21T10:00:00", "2026-06-20T10:00:00"]),
        }
        guards = []

        def factory():
            guard = ReadOnlyGuard(_VelocityFanoutClient(data))
            guards.append(guard)
            return guard

        payload = cockpit_read.velocity_payload(
            14, now=T_NOW, client_factory=factory
        )

        # Every tenant read through the velocity path issued zero writes.
        self.assertGreaterEqual(len(guards), 4)
        for guard in guards:
            self.assertEqual(guard.write_calls, [])

        # The aggregate is all-OK; alice's figure sums the three tenants with the
        # per-tenant breakdown (composed, never joined).
        self.assertEqual(payload["aggregateStatus"], 200)
        rows = {row["personKey"]: row for row in payload["rows"]}
        self.assertEqual(rows["alice@example.com"]["count"], 9)
        self.assertEqual(
            rows["alice@example.com"]["perTenant"], {"alpha": 4, "beta": 3, "gamma": 2}
        )
        self.assertEqual(payload["window"], 14)

        # Each per-tenant client bound its tenant before reading its issues.
        read_guards = [g for g in guards if "list_issues" in g._target.calls]
        self.assertEqual(len(read_guards), 3)
        for guard in read_guards:
            calls = guard._target.calls
            first_read = calls.index("list_issues")
            bound_before = [
                index
                for index, call in enumerate(calls)
                if isinstance(call, tuple) and call[0] == "use_tenant" and index < first_read
            ]
            self.assertTrue(bound_before, f"read before bind: {calls}")


class TestVelocityCli(unittest.TestCase):
    def test_velocity_cli_outputs_velocity_json(self):
        """main(["velocity", "--window", "14"]) prints the per-user velocity JSON
        (rows, window, aggregateStatus) for the Node bridge, wiring the window
        argument through to velocity_payload."""
        # A delivery a minute ago is inside any window relative to the wall clock,
        # so the row count is deterministic without injecting now into the CLI.
        recent = (datetime.now() - timedelta(seconds=60)).isoformat(timespec="seconds")
        data = {
            "solo": {
                "issues": [
                    {"github_id": "s1", "status": "closed", "assignee": "alice@example.com"}
                ],
                "history": {"s1": _done_history(recent)},
            }
        }
        out = io.StringIO()
        with patch(
            "solomon_harness.cockpit_read.DatabaseClient",
            side_effect=lambda *args, **kwargs: _VelocityFanoutClient(data),
        ):
            with contextlib.redirect_stdout(out):
                rc = cockpit_read.main(["velocity", "--window", "14"])

        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["window"], 14)
        self.assertEqual(printed["aggregateStatus"], 200)
        rows = {row["personKey"]: row for row in printed["rows"]}
        self.assertEqual(rows["alice@example.com"]["count"], 1)


class TestEpicTracking(unittest.TestCase):
    def test_epic_exists(self):
        import solomon_harness.cockpit_read as cockpit
        self.assertIsNotNone(cockpit)



if __name__ == "__main__":
    unittest.main()

