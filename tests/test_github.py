import json
import unittest
from unittest.mock import patch

from solomon_harness import github


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestGhWrapper(unittest.TestCase):
    def test_gh_missing_is_handled(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            res = github._gh(["repo", "view"])
        self.assertFalse(res["ok"])
        self.assertIn("gh CLI not found", res["error"])

    def test_gh_nonzero_returns_error(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            res = github._gh(["repo", "view"])
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "boom")

    def test_gh_parses_json(self):
        with patch("subprocess.run", return_value=_Proc(0, '{"a": 1}')):
            res = github._gh(["x"], parse_json=True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"], {"a": 1})


class TestEnsureBoard(unittest.TestCase):
    def test_returns_existing_without_creating(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": [{"title": "solomon", "number": 4}]}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertFalse(res["created"])
        self.assertEqual(res["project"]["number"], 4)
        self.assertFalse(any(c[:3] == ["gh", "project", "create"] for c in calls))

    def test_creates_when_absent(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            if cmd[:3] == ["gh", "project", "create"]:
                return _Proc(0, json.dumps({"number": 9, "title": "solomon"}))
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                self._graphql_calls.append(cmd)
                return _Proc(0, "{}")
            raise AssertionError(f"unexpected gh call: {cmd}")

        self._graphql_calls = []
        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertTrue(res["created"])
        self.assertEqual(res["project"]["number"], 9)
        self.assertTrue(res["columns_configured"])
        # The create path must push every lifecycle column as a single-select option.
        self.assertEqual(len(self._graphql_calls), 1)
        mutation = self._graphql_calls[0][-1]
        for col in github.BOARD_COLUMNS:
            self.assertIn(f'name: "{col}"', mutation)


class TestConfigureBoardColumns(unittest.TestCase):
    def test_missing_project_number_is_handled(self):
        res = github._configure_board_columns("acme", None)
        self.assertFalse(res["ok"])

    def test_builds_mutation_with_all_columns(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                return _Proc(0, "{}")
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github._configure_board_columns("acme", 9)
        self.assertTrue(res["ok"])


class TestEnsureLabels(unittest.TestCase):
    def test_creates_every_standard_label(self):
        created = []

        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd[:3], ["gh", "label", "create"])
            created.append(cmd[3])
            return _Proc(0, "")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_labels()
        self.assertTrue(res["ok"])
        self.assertEqual(created, [name for name, _c, _d in github.STANDARD_LABELS])

    def test_partial_failure_is_not_ok(self):
        def fake_run(cmd, **kwargs):
            if cmd[3] == "type:bug":
                return _Proc(1, "", "boom")
            return _Proc(0, "")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_labels()
        self.assertFalse(res["ok"])
        self.assertNotIn("type:bug", res["labels"])


class TestSetStatus(unittest.TestCase):
    def test_rejects_unknown_status(self):
        res = github.set_issue_status(1, "Nope")
        self.assertFalse(res["ok"])
        self.assertIn("unknown status", res["error"])

    def test_known_status_is_allowed(self):
        self.assertIn("Code Review", github.BOARD_COLUMNS)
        self.assertIn("QA", github.BOARD_COLUMNS)


class TestRecordTransition(unittest.TestCase):
    def test_appends_timeline_entry(self):
        import tempfile

        from solomon_harness.tools.database_client import DatabaseClient

        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.getcwd", return_value=tmp):
                github.record_transition(7, "In Progress")
                github.record_transition(7, "Code Review")
                with DatabaseClient(harness_dir=tmp) as db:
                    raw = db.get_memory("board_history:7")
            history = json.loads(raw)
        self.assertEqual([h["column"] for h in history], ["In Progress", "Code Review"])
        self.assertTrue(all("entered_at" in h for h in history))

    def test_never_raises_on_failure(self):
        with patch("solomon_harness.tools.database_client.DatabaseClient", side_effect=RuntimeError):
            # Best-effort: a DB failure must not propagate.
            github.record_transition(1, "Done")


class TestBoardTitleAndLink(unittest.TestCase):
    def test_board_title_includes_repo_name(self):
        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["gh", "repo", "view", "--json"] and cmd[4] == "name":
                return _Proc(0, json.dumps({"name": "widget"}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(github.board_title(), "solomon - widget")

    def test_board_title_falls_back_when_repo_unknown(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "no repo")):
            self.assertEqual(github.board_title(), "solomon")

    def test_create_links_board_to_repo(self):
        links = []

        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["gh", "repo", "view", "--json"]:
                field = cmd[4]
                data = {
                    "owner": {"owner": {"login": "acme"}},
                    "name": {"name": "widget"},
                    "nameWithOwner": {"nameWithOwner": "acme/widget"},
                }[field]
                return _Proc(0, json.dumps(data))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            if cmd[:3] == ["gh", "project", "create"]:
                return _Proc(0, json.dumps({"number": 9, "title": "solomon - widget"}))
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                return _Proc(0, "{}")
            if cmd[:3] == ["gh", "project", "link"]:
                links.append(cmd)
                return _Proc(0, "")
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["created"])
        self.assertTrue(res["linked_to_repo"])
        # The board was created with the repo-aware title and linked to the repo.
        self.assertEqual(res["project"]["title"], "solomon - widget")
        self.assertEqual(len(links), 1)
        self.assertIn("acme/widget", links[0])


if __name__ == "__main__":
    unittest.main()
