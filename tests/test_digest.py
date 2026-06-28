"""Tests for the session-start board digest (Phase 1).

The digest is facts-only: it renders what the harness already knows (resume
point, open work, the last loop run, PRs awaiting review) and points at
/solomon-loop to decide the next step. It never computes the next step itself —
that stays the canonical prose ladder in the loop command.
"""

import unittest

from solomon_harness import digest


class TestBuildDigest(unittest.TestCase):
    def test_full_digest(self):
        lines = digest.build_digest(
            resume={"type": "session", "agent": "qa", "task": "review PR #27", "status": "active"},
            open_issues=[{"github_id": "bug-x", "title": "T1"}, {"github_id": "bug-y", "title": "T2"}],
            last_loop_run={"stage": "start", "target": "42", "status": "ok", "created_at": "2026-06-28T10:00:00"},
            prs=[
                {"number": 31, "title": "feat: x", "reviewDecision": None, "isDraft": False},
                {"number": 32, "title": "wip", "reviewDecision": None, "isDraft": True},
                {"number": 33, "title": "done", "reviewDecision": "APPROVED", "isDraft": False},
            ],
        )
        text = "\n".join(lines)
        self.assertIn("review PR #27", text)
        self.assertIn("/solomon-start 42 -> ok", text)
        self.assertIn("Open issues: 2", text)
        self.assertIn("PRs awaiting review: 1", text)  # only #31: not draft, not approved
        self.assertIn("#31", text)
        self.assertNotIn("#32", text)  # drafts excluded
        self.assertNotIn("#33", text)  # approved excluded
        self.assertIn("run /solomon-loop", text)

    def test_empty_digest_degrades_cleanly(self):
        text = "\n".join(digest.build_digest(resume=None, open_issues=[], last_loop_run=None, prs=None))
        self.assertIn("no prior activity", text)
        self.assertIn("Open issues: 0", text)
        self.assertIn("gh unavailable", text)
        self.assertIn("run /solomon-loop", text)

    def test_open_issue_list_is_capped(self):
        many = [{"github_id": f"i{i}", "title": f"T{i}"} for i in range(9)]
        text = "\n".join(digest.build_digest(resume=None, open_issues=many, last_loop_run=None, prs=[]))
        self.assertIn("Open issues: 9", text)
        self.assertIn("and 4 more", text)  # 5 shown, 4 elided

    def test_gather_digest_uses_db_without_github(self):
        class FakeDB:
            def get_latest_activity(self):
                return {"type": "session", "agent": "qa", "task": "t", "status": "active"}

            def get_open_issues(self):
                return [{"github_id": "x", "title": "T"}]

            def list_loop_runs(self, n):
                return [{"stage": "loop", "target": "", "status": "ok", "created_at": "2026-06-28T10:00:00"}]

        text = "\n".join(digest.gather_digest(".", FakeDB(), fetch_github=False))
        self.assertIn("Resume:", text)
        self.assertIn("Last loop:", text)
        self.assertIn("Open issues: 1", text)

    def test_gather_digest_survives_a_broken_db(self):
        class BrokenDB:
            def get_latest_activity(self):
                raise RuntimeError("backend down")

            def get_open_issues(self):
                raise RuntimeError("backend down")

            def list_loop_runs(self, n):
                raise RuntimeError("backend down")

        # A broken memory backend must not break session start.
        text = "\n".join(digest.gather_digest(".", BrokenDB(), fetch_github=False))
        self.assertIn("run /solomon-loop", text)


if __name__ == "__main__":
    unittest.main()
