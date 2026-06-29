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
        self.assertIn("/solomon-release 33", text)

    def test_empty_digest_degrades_cleanly(self):
        text = "\n".join(digest.build_digest(resume=None, open_issues=[], last_loop_run=None, prs=None))
        self.assertIn("no prior activity", text)
        self.assertIn("Open issues: 0", text)
        self.assertIn("gh unavailable", text)
        self.assertIn("/solomon-idea", text)

    def test_terminal_issues_excluded_from_count_and_list(self):
        """build_digest defensively drops terminal rows (closed/done/Done) from
        both the count and the rendered list, even if handed a stale open_issues
        list, so the resume digest never shows delivered work (ADR-0006)."""
        issues = [
            {"github_id": "a", "title": "active", "status": "in_progress"},
            {"github_id": "b", "title": "closed one", "status": "closed"},
            {"github_id": "c", "title": "done token", "status": "done"},
            {"github_id": "d", "title": "legacy done", "status": "Done"},
            {"github_id": "e", "title": "backlog", "status": "Backlog"},
        ]
        text = "\n".join(
            digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=None)
        )
        self.assertIn("Open issues: 2", text)
        self.assertIn("[a]", text)
        self.assertIn("[e]", text)
        self.assertNotIn("[b]", text)
        self.assertNotIn("[c]", text)
        self.assertNotIn("[d]", text)

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
        self.assertIn("Options to proceed", text)

    def test_digest_shows_pending_task_options(self):
        # Case 1: Approved PR -> release
        prs = [{"number": 12, "title": "fix auth", "reviewDecision": "APPROVED", "isDraft": False}]
        text = "\n".join(digest.build_digest(resume=None, open_issues=[], last_loop_run=None, prs=prs))
        self.assertIn("We found a pending task: Release approved PR #12", text)
        self.assertIn("1. Single Step (Recommended): Run /solomon-release 12", text)

        # Case 2: Open PR awaiting review -> review
        prs = [{"number": 15, "title": "add feature", "reviewDecision": "REVIEW_REQUIRED", "isDraft": False}]
        text = "\n".join(digest.build_digest(resume=None, open_issues=[], last_loop_run=None, prs=prs))
        self.assertIn("We found a pending task: Review open PR #15", text)
        self.assertIn("1. Single Step (Recommended): Run /solomon-review 15", text)

    def test_digest_shows_no_pending_task_options(self):
        # No pending tasks -> lists github open issues (ideas/backlog) and their refine/issue commands
        issues = [
            {"github_id": "45", "title": "fix login", "status": "backlog"},
            {"github_id": "46", "title": "new profile", "status": "ideas"}
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("GitHub Open Issues:", text)
        self.assertIn("Refine/Start Issue #45: /solomon-refine 45", text)
        self.assertIn("Refine/Start Issue #46: /solomon-issue 46", text)
        self.assertIn("Capture a new product idea: /solomon-idea", text)

    def test_digest_shows_in_flight_review_qa(self):
        issues = [
            {"github_id": "100", "title": "review this", "status": "code_review"}
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("We found a pending task: Review/QA issue #100", text)
        self.assertIn("/solomon-review 100", text)

        issues = [
            {"github_id": "101", "title": "qa this", "status": "qa"}
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("We found a pending task: Review/QA issue #101", text)
        self.assertIn("/solomon-review 101", text)

    def test_digest_shows_resume_start_active(self):
        resume = {"type": "session", "agent": "qa", "task": "start 42", "status": "active"}
        text = "\n".join(digest.build_digest(resume=resume, open_issues=[], last_loop_run=None, prs=[]))
        self.assertIn("Resume last activity: qa is working on 'start 42'", text)
        self.assertIn("/solomon-start 42", text)

    def test_digest_shows_ready_issues(self):
        issues = [
            {"github_id": "200", "title": "ready to work", "status": "ready"}
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("We found a pending task: Start development on Ready issue #200", text)
        self.assertIn("/solomon-start 200", text)

    def test_best_effort_prs_success(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '[{"number": 1, "title": "PR 1", "reviewDecision": "APPROVED", "isDraft": false}]'
            mock_run.return_value = mock_proc
            res = digest._best_effort_prs(".")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["number"], 1)

    def test_best_effort_prs_failure(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""
            mock_run.return_value = mock_proc
            res = digest._best_effort_prs(".")
            self.assertIsNone(res)

    def test_best_effort_prs_exception(self):
        from unittest.mock import patch
        with patch("subprocess.run", side_effect=RuntimeError("timeout")):
            res = digest._best_effort_prs(".")
            self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
