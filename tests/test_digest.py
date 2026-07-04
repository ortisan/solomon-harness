"""Tests for the session-start board digest (Phase 1).

The digest is facts-only: it renders what the harness already knows (resume
point, open work, the last loop run, PRs awaiting review) and points at
/solomon-workflow to decide the next step. It never computes the next step itself —
that stays the canonical prose ladder in the loop command.
"""

import re
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
        self.assertIn("Open issues: 0 GitHub issues, 2 tracking items", text)
        self.assertIn("PRs awaiting review: 1", text)  # only #31: not draft, not approved
        self.assertIn("#31", text)
        self.assertNotIn("#32", text)  # drafts excluded
        self.assertIn("/solomon-release 33", text)

    def test_empty_digest_degrades_cleanly(self):
        text = "\n".join(digest.build_digest(resume=None, open_issues=[], last_loop_run=None, prs=None))
        self.assertIn("no prior activity", text)
        self.assertIn("Open issues: 0 GitHub issues, 0 tracking items", text)
        self.assertIn("gh unavailable", text)
        self.assertIn("/solomon-idea", text)

    def test_open_issues_line_splits_github_and_tracking(self):
        """The Open issues line reports two figures: real GitHub issues (numeric id)
        and tracking items (composite/empty id), never one conflated total (#116)."""
        issues = [
            {"github_id": "116", "title": "Real issue"},
            {"github_id": "116-R-01", "title": "RAID follow-up"},
            {"github_id": "", "title": "Tracking item"},
        ]
        text = "\n".join(
            digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=None)
        )
        self.assertIn("Open issues: 1 GitHub issues, 2 tracking items", text)
        self.assertNotIn("Open issues: 3", text)  # never a conflated single total

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
        self.assertIn("Open issues: 0 GitHub issues, 2 tracking items", text)
        self.assertIn("[a]", text)
        self.assertIn("[e]", text)
        self.assertNotIn("[b]", text)
        self.assertNotIn("[c]", text)
        self.assertNotIn("[d]", text)

    def test_open_issues_buckets_are_digits_only_and_sum_to_total(self):
        """The GitHub bucket counts a numeric id only (not a composite id sharing
        its digits, not a terminal row), and github + tracking always sums to the
        rendered non-terminal total -- segregating, never dropping a row (#116)."""
        issues = [
            {"github_id": "116", "title": "Real issue"},
            {"github_id": "116-R-01", "title": "Shares digits, not a GitHub issue"},
            {"github_id": "bug-x", "title": "Slug tracking"},
            {"github_id": "", "title": "Empty tracking"},
            {"github_id": "999", "title": "Terminal numeric", "status": "closed"},
        ]
        text = "\n".join(
            digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=None)
        )
        match = re.search(r"Open issues: (\d+) GitHub issues, (\d+) tracking items", text)
        self.assertIsNotNone(match)
        github_count, tracking_count = int(match.group(1)), int(match.group(2))
        self.assertEqual(github_count, 1)  # only 116, not 116-R-01, not terminal 999
        self.assertEqual(tracking_count, 3)  # 116-R-01, bug-x, empty
        # No-deletion: the two buckets sum to the non-terminal total (4), and the
        # terminal numeric 999 leaks into neither bucket nor the rendered list.
        self.assertEqual(github_count + tracking_count, 4)
        self.assertNotIn("999", text)

    def test_open_issue_list_is_capped(self):
        many = [{"github_id": f"i{i}", "title": f"T{i}"} for i in range(9)]
        text = "\n".join(digest.build_digest(resume=None, open_issues=many, last_loop_run=None, prs=[]))
        self.assertIn("Open issues: 0 GitHub issues, 9 tracking items", text)
        self.assertIn("and 4 more", text)  # 5 shown, 4 elided

    def test_gather_digest_uses_db_without_github(self):
        class FakeDB:
            def get_latest_activity(self):
                return {"type": "session", "agent": "qa", "task": "t", "status": "active"}

            def get_open_issues(self):
                return [{"github_id": "x", "title": "T"}]

            def list_loop_runs(self, n):
                return [{"stage": "workflow", "target": "", "status": "ok", "created_at": "2026-06-28T10:00:00"}]

        text = "\n".join(digest.gather_digest(".", FakeDB(), fetch_github=False))
        self.assertIn("Resume:", text)
        self.assertIn("Last loop:", text)
        self.assertIn("Open issues: 0 GitHub issues, 1 tracking items", text)

    def test_build_digest_flags_sqlite_fallback(self):
        """When memory is on the SQLite fallback (SurrealDB unreachable), the
        digest must say so loudly, so fallback rows are never mistaken for the
        canonical board state."""
        text = "\n".join(
            digest.build_digest(
                resume=None, open_issues=[], last_loop_run=None, prs=None, backend="sqlite"
            )
        )
        self.assertIn("SQLite fallback", text)
        self.assertIn("may be stale", text)

    def test_build_digest_no_banner_on_surreal(self):
        text = "\n".join(
            digest.build_digest(
                resume=None, open_issues=[], last_loop_run=None, prs=None, backend="surrealdb"
            )
        )
        self.assertNotIn("SQLite fallback", text)

    def test_gather_digest_surfaces_sqlite_fallback(self):
        class FallbackDB:
            backend = "sqlite"

            def get_latest_activity(self):
                return None

            def get_open_issues(self):
                return []

            def list_loop_runs(self, n):
                return []

        text = "\n".join(digest.gather_digest(".", FallbackDB(), fetch_github=False))
        self.assertIn("SQLite fallback", text)

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

    def test_digest_resume_without_issue_hint_points_at_the_orchestrator(self):
        resume = {"type": "session", "agent": "qa", "task": "triaging things", "status": "active"}
        text = "\n".join(digest.build_digest(resume=resume, open_issues=[], last_loop_run=None, prs=[]))
        self.assertIn("/solomon-workflow", text)

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

    def test_best_effort_prs_strips_inherited_git_env(self):
        # A leaked GIT_DIR/GIT_WORK_TREE (e.g. from a git hook or another
        # worktree) must not be forwarded to the gh subprocess.
        import os
        from unittest.mock import patch, MagicMock
        leaked = {"GIT_DIR": "/tmp/leaked/.git", "GIT_WORK_TREE": "/tmp/leaked"}
        with patch.dict(os.environ, leaked):
            with patch("subprocess.run") as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = "[]"
                mock_run.return_value = mock_proc
                digest._best_effort_prs(".")
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env, "gh subprocess must receive an explicit, scrubbed env")
        self.assertFalse(any(k.startswith("GIT_") for k in env))

    def test_safe_id_edge_cases(self):
        self.assertIsNone(digest._safe_id(None))
        self.assertIsNone(digest._safe_id("invalid; rm -rf /"))
        self.assertEqual(digest._safe_id("123-abc_def"), "123-abc_def")

    def test_sanitize_title_none(self):
        self.assertEqual(digest._sanitize_title(None), "")

    def test_resume_uses_graph_linked_issue_over_task_text(self):
        # ADR-0017: the worked_on edges name the issue; no number in the task
        # text is needed (the legacy regex would have found nothing here).
        resume = {
            "type": "session", "agent": "software_engineer",
            "task": "implement the widget", "status": "active", "issues": [42],
        }
        per_issue = [
            {"github_id": "42", "title": "The widget", "issue_status": "in_progress"}
        ]
        text = "\n".join(
            digest.build_digest(
                resume=resume, open_issues=[], last_loop_run=None, prs=[],
                per_issue=per_issue,
            )
        )
        self.assertIn("/solomon-start 42", text)
        self.assertIn(
            "Resume last activity: software_engineer is working on 'implement the widget'",
            text,
        )

    def test_resume_graph_maps_review_status_to_review(self):
        resume = {
            "type": "session", "agent": "qa",
            "task": "verify the fix", "status": "active", "issues": [77],
        }
        per_issue = [
            {"github_id": "77", "title": "The fix", "issue_status": "code_review"}
        ]
        text = "\n".join(
            digest.build_digest(
                resume=resume, open_issues=[], last_loop_run=None, prs=[],
                per_issue=per_issue,
            )
        )
        self.assertIn("/solomon-review 77", text)

    def test_resume_graph_rows_win_even_without_resume_issues_key(self):
        # A legacy resume row with no edges of its own still gets a typed
        # target when the per-issue graph has rows.
        resume = {
            "type": "session", "agent": "qa",
            "task": "start something", "status": "active",
        }
        per_issue = [
            {"github_id": "9", "title": "Recent", "issue_status": "in_progress"}
        ]
        text = "\n".join(
            digest.build_digest(
                resume=resume, open_issues=[], last_loop_run=None, prs=[],
                per_issue=per_issue,
            )
        )
        self.assertIn("/solomon-start 9", text)

    def test_resume_without_graph_rows_falls_back_to_the_regex(self):
        # The deprecated free-text branch (ADR-0017) still resolves legacy
        # sessions with no worked_on edges.
        resume = {"type": "session", "agent": "qa", "task": "start #55", "status": "active"}
        text = "\n".join(
            digest.build_digest(
                resume=resume, open_issues=[], last_loop_run=None, prs=[],
                per_issue=[],
            )
        )
        self.assertIn("/solomon-start 55", text)

    def test_gather_digest_feeds_per_issue_rows(self):
        class GraphDB:
            backend = "surrealdb"

            def get_latest_activity(self):
                return {
                    "type": "session", "agent": "qa",
                    "task": "no number here", "status": "active",
                }

            def get_open_issues(self):
                return []

            def list_loop_runs(self, limit):
                return []

            def latest_activity_per_issue(self, limit=10):
                return [
                    {"github_id": "31", "title": "Linked", "issue_status": "in_progress"}
                ]

        lines = digest.gather_digest(".", GraphDB(), fetch_github=False)
        self.assertIn("/solomon-start 31", "\n".join(lines))

    def test_digest_shows_resume_start_active_with_hash(self):
        resume = {"type": "session", "agent": "qa", "task": "start #123", "status": "active"}
        text = "\n".join(digest.build_digest(resume=resume, open_issues=[], last_loop_run=None, prs=[]))
        self.assertIn("/solomon-start 123", text)

    def test_digest_shows_resume_start_active_with_word_issue(self):
        resume = {"type": "session", "agent": "qa", "task": "start issue 456", "status": "active"}
        text = "\n".join(digest.build_digest(resume=resume, open_issues=[], last_loop_run=None, prs=[]))
        self.assertIn("/solomon-start 456", text)

    def test_digest_option_command_mappings(self):
        # We test backlog -> refine, ideas -> issue, ready -> start, and code_review -> review
        # To make sure they are in the first 3 options, we split into two runs
        issues = [
            {"github_id": "11", "title": "backlog issue", "status": "backlog"},
            {"github_id": "12", "title": "ideas issue", "status": "ideas"},
            {"github_id": "13", "title": "ready issue", "status": "ready"},
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("/solomon-refine 11", text)
        self.assertIn("/solomon-issue 12", text)
        self.assertIn("/solomon-start 13", text)

        issues2 = [
            {"github_id": "14", "title": "code review issue", "status": "code_review"},
            {"github_id": "15", "title": "qa issue", "status": "qa"},
        ]
        text2 = "\n".join(digest.build_digest(resume=None, open_issues=issues2, last_loop_run=None, prs=[]))
        self.assertIn("/solomon-review 14", text2)
        self.assertIn("/solomon-review 15", text2)

    def test_digest_sanitizes_github_id(self):
        issues = [
            {"github_id": "bad\x1bid", "title": "issue title", "status": "backlog"}
        ]
        text = "\n".join(digest.build_digest(resume=None, open_issues=issues, last_loop_run=None, prs=[]))
        self.assertIn("- [badid] issue title", text)

    def test_run_with_timeout_distinguishes_immediate_failure_from_timeout(self):
        import io
        import time
        from unittest.mock import patch
        
        # Test 1: Immediate failure (should NOT print warning to stderr)
        def fail_immediately():
            raise RuntimeError("DB failed")
            
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            res = digest._run_with_timeout(fail_immediately, timeout=0.1, default="fallback")
            self.assertEqual(res, "fallback")
            self.assertEqual(stderr_capture.getvalue(), "")

        # Test 2: Timeout/Hang (should print warning to stderr)
        def hang_long():
            time.sleep(0.5)
            return "ok"
            
        stderr_capture2 = io.StringIO()
        with patch("sys.stderr", stderr_capture2):
            res2 = digest._run_with_timeout(hang_long, timeout=0.1, default="fallback")
            self.assertEqual(res2, "fallback")
            self.assertIn("timed out after 0.1 seconds", stderr_capture2.getvalue())


if __name__ == "__main__":
    unittest.main()
