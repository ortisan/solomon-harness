"""Milestone lifecycle write-through and the release collision guard (#176)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import github
from solomon_harness.tools.database_client import DatabaseClient


def _fake_gh(rules):
    """A fake _gh: ``rules`` is a list of (predicate(args) -> bool, response)."""
    calls = []

    def run(args, parse_json=False, **kwargs):
        calls.append(args)
        for predicate, response in rules:
            if predicate(args):
                return response
        return {"ok": False, "error": "unmatched"}

    run.calls = calls
    return run


def _client(tmp):
    return DatabaseClient(
        harness_dir=tmp,
        db_path=os.path.join(tmp, "memory.db"),
        mirror_root=os.path.join(tmp, "mirror"),
    )


class TestMemoryMilestoneLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _client(self.tmp.name)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _titles(self):
        return [m.get("title") for m in self.db.list_milestones()]

    def test_ensure_milestone_is_idempotent_by_title(self):
        first = self.db.ensure_milestone("v0.4.0", "Epic", "2026-08-01")
        second = self.db.ensure_milestone("v0.4.0")
        self.assertEqual(self._titles().count("v0.4.0"), 1)  # no duplicate row
        self.assertEqual(str(first), str(second))

    def test_close_milestone_writes_terminal_state(self):
        self.db.ensure_milestone("v0.4.0")
        self.db.close_milestone("v0.4.0")
        row = self.db.get_milestone_by_title("v0.4.0")
        self.assertEqual(row.get("state"), "closed")
        # Idempotent: a second close does not duplicate the row.
        self.db.close_milestone("v0.4.0")
        self.assertEqual(self._titles().count("v0.4.0"), 1)
        self.assertEqual(self.db.get_milestone_by_title("v0.4.0").get("state"), "closed")

    def test_close_unknown_milestone_records_it_closed(self):
        self.db.close_milestone("v9.9.9")
        row = self.db.get_milestone_by_title("v9.9.9")
        self.assertIsNotNone(row)
        self.assertEqual(row.get("state"), "closed")


class TestGithubMilestoneSeams(unittest.TestCase):
    def setUp(self):
        self.nwo = patch("solomon_harness.github.repo_name_with_owner", return_value="o/r")
        self.nwo.start()

    def tearDown(self):
        self.nwo.stop()

    def test_ensure_creates_when_missing(self):
        gh = _fake_gh([
            (lambda a: a[0] == "api" and "milestones?state=all" in a[1], {"ok": True, "data": []}),
            (lambda a: a[0] == "api" and a[1].endswith("/milestones"), {"ok": True, "data": {"number": 7}}),
        ])
        self.assertEqual(github.ensure_github_milestone("v0.4.0", gh=gh), 7)

    def test_ensure_returns_existing_without_creating(self):
        gh = _fake_gh([
            (lambda a: "state=all" in a[1], {"ok": True, "data": [{"title": "v0.4.0", "number": 3}]}),
        ])
        self.assertEqual(github.ensure_github_milestone("v0.4.0", gh=gh), 3)
        # No POST create call was made (only the list query).
        self.assertTrue(all("state=all" in a[1] for a in gh.calls))

    def test_ensure_degrades_when_gh_fails(self):
        gh = _fake_gh([(lambda a: True, {"ok": False, "error": "no scope"})])
        self.assertIsNone(github.ensure_github_milestone("v0.4.0", gh=gh))

    def test_assign_returns_ok_flag(self):
        gh_ok = _fake_gh([(lambda a: a[:2] == ["issue", "edit"], {"ok": True, "stdout": ""})])
        self.assertTrue(github.assign_issue_to_github_milestone(5, "v0.4.0", gh=gh_ok))
        gh_bad = _fake_gh([(lambda a: True, {"ok": False, "error": "x"})])
        self.assertFalse(github.assign_issue_to_github_milestone(5, "v0.4.0", gh=gh_bad))

    def test_close_patches_the_matched_number(self):
        gh = _fake_gh([
            (lambda a: "state=all" in a[1], {"ok": True, "data": [{"title": "v0.4.0", "number": 9}]}),
            (lambda a: "PATCH" in a, {"ok": True, "data": {"state": "closed"}}),
        ])
        self.assertTrue(github.close_github_milestone("v0.4.0", gh=gh))
        self.assertTrue(
            any("PATCH" in a and any("/milestones/9" in str(x) for x in a) for a in gh.calls)
        )

    def test_close_missing_milestone_returns_false(self):
        gh = _fake_gh([(lambda a: "state=all" in a[1], {"ok": True, "data": []})])
        self.assertFalse(github.close_github_milestone("v9.9.9", gh=gh))

    def test_list_open_shapes_rows(self):
        gh = _fake_gh([
            (lambda a: "state=open" in a[1], {"ok": True, "data": [
                {"title": "v0.4.0", "number": 1, "open_issues": 3},
                {"title": "theme", "number": 2, "open_issues": 0},
            ]}),
        ])
        rows = github.list_open_github_milestones(gh=gh)
        self.assertEqual(rows[0], {"title": "v0.4.0", "number": 1, "open_issues": 3})


class TestMilestoneOrchestrators(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "HARNESS_DB_PATH": os.path.join(self.tmp.name, "m.db"),
                "HARNESS_MIRROR_ROOT": os.path.join(self.tmp.name, "mirror"),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_assign_everywhere_mirrors_memory(self):
        with patch("solomon_harness.github.ensure_github_milestone", return_value=5), patch(
            "solomon_harness.github.assign_issue_to_github_milestone", return_value=True
        ):
            res = github.assign_milestone_everywhere(self.tmp.name, 42, "v0.4.0")
        self.assertTrue(res["ok"])
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            self.assertIsNotNone(db.get_milestone_by_title("v0.4.0"))

    def test_close_everywhere_writes_memory_terminal(self):
        with patch("solomon_harness.github.close_github_milestone", return_value=True):
            res = github.close_milestone_everywhere(self.tmp.name, "v0.4.0")
        self.assertTrue(res["github_closed"])
        self.assertTrue(res["memory"])
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            self.assertEqual(db.get_milestone_by_title("v0.4.0").get("state"), "closed")

    def test_close_everywhere_degrades_when_github_fails(self):
        # A gh scope failure must still write memory and never raise.
        with patch("solomon_harness.github.close_github_milestone", return_value=False):
            res = github.close_milestone_everywhere(self.tmp.name, "v0.5.0")
        self.assertFalse(res["ok"])
        self.assertTrue(res["memory"])
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            self.assertEqual(db.get_milestone_by_title("v0.5.0").get("state"), "closed")


class TestMilestoneReconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "HARNESS_DB_PATH": os.path.join(self.tmp.name, "m.db"),
                "HARNESS_MIRROR_ROOT": os.path.join(self.tmp.name, "mirror"),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_delete_milestone_by_title(self):
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            db.ensure_milestone("junk")
            self.assertIsNotNone(db.get_milestone_by_title("junk"))
            self.assertEqual(db.delete_milestone_by_title("junk"), 1)
            self.assertIsNone(db.get_milestone_by_title("junk"))

    def test_reconcile_closes_zeroed_and_prunes_only_junk(self):
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            db.ensure_milestone("v0.4.0")  # SemVer -> keep
            db.ensure_milestone("test-ci-hardening")  # real theme milestone -> keep
            db.ensure_milestone("Sprint 1")  # junk -> prune
            db.ensure_milestone("m")  # junk -> prune
        with patch(
            "solomon_harness.github.list_open_github_milestones",
            return_value=[{"title": "v0.4.0", "number": 1, "open_issues": 0}],
        ), patch(
            "solomon_harness.github._all_github_milestone_titles",
            return_value={"v0.4.0", "test-ci-hardening"},
        ), patch(
            "solomon_harness.github.close_github_milestone", return_value=True
        ):
            res = github.reconcile_milestones(self.tmp.name)
        self.assertIn("v0.4.0", [c["title"] for c in res["closed"]])
        self.assertIn("Sprint 1", res["pruned"])
        self.assertIn("m", res["pruned"])
        self.assertIn("v0.4.0", res["kept"])
        self.assertIn("test-ci-hardening", res["kept"])
        with DatabaseClient(harness_dir=self.tmp.name) as db:
            titles = [m.get("title") for m in db.list_milestones()]
        self.assertNotIn("Sprint 1", titles)
        self.assertNotIn("m", titles)
        self.assertIn("v0.4.0", titles)
        self.assertIn("test-ci-hardening", titles)


class TestReleaseCollisionGuard(unittest.TestCase):
    def setUp(self):
        from solomon_harness import release

        self.release = release
        self.info = {
            "next": "0.12.0",
            "level": "minor",
            "base": "0.11.0",
            "last_tag": "v0.11.0",
            "commit_count": 1,
            "commits": [],
        }

    def test_pure_collision_detection(self):
        col = self.release.milestone_collision
        self.assertEqual(col("0.12.0", [{"title": "v0.12.0", "open_issues": 3}]), "v0.12.0")
        # Bare version form also matches.
        self.assertEqual(col("0.12.0", [{"title": "0.12.0", "open_issues": 1}]), "0.12.0")
        # A milestone already at 0 open issues is ready to release: no collision.
        self.assertIsNone(col("0.12.0", [{"title": "v0.12.0", "open_issues": 0}]))
        # An unrelated open milestone does not collide.
        self.assertIsNone(col("0.12.0", [{"title": "theme", "open_issues": 5}]))
        self.assertIsNone(col(None, [{"title": "v0.12.0", "open_issues": 3}]))

    def test_cmd_plan_fails_on_collision(self):
        with patch("solomon_harness.release.plan", return_value=self.info), patch(
            "solomon_harness.github.list_open_github_milestones",
            return_value=[{"title": "v0.12.0", "open_issues": 3}],
        ):
            self.assertEqual(self.release.cmd_plan("/x"), 1)

    def test_cmd_plan_succeeds_without_collision(self):
        with patch("solomon_harness.release.plan", return_value=self.info), patch(
            "solomon_harness.github.list_open_github_milestones",
            return_value=[{"title": "v0.12.0", "open_issues": 0}],
        ):
            self.assertEqual(self.release.cmd_plan("/x"), 0)

    def test_cmd_plan_degrades_when_gh_unavailable(self):
        with patch("solomon_harness.release.plan", return_value=self.info), patch(
            "solomon_harness.github.list_open_github_milestones",
            side_effect=Exception("no gh"),
        ):
            # gh down must never block the release.
            self.assertEqual(self.release.cmd_plan("/x"), 0)


if __name__ == "__main__":
    unittest.main()
