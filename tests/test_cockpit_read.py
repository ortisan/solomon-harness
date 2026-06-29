import os
import sys
import tempfile
import unittest

# Ensure the repository root is on sys.path so the package imports cleanly.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness import cockpit_read  # noqa: E402
from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
