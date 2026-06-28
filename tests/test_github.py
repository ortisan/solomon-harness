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
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertTrue(res["created"])
        self.assertEqual(res["project"]["number"], 9)


class TestSetStatus(unittest.TestCase):
    def test_rejects_unknown_status(self):
        res = github.set_issue_status(1, "Nope")
        self.assertFalse(res["ok"])
        self.assertIn("unknown status", res["error"])

    def test_known_status_is_allowed(self):
        self.assertIn("In Review", github.BOARD_COLUMNS)


if __name__ == "__main__":
    unittest.main()
