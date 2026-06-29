import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
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
from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
