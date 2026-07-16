"""Three-way parity fixture for the open-issues read paths (#297, Requirement 4).

``digest.gather_digest``, ``MemoryService.get_open_issues``, and
``github.list_open_issues`` each apply claim-aware filtering independently
(digest.py, memory_service.py:97-129, github.py:451-490). Requirement #4 of
docs/specs/297-digest-filters-claimed-issues.md calls for a shared fixture
that proves the three agree on the same input, so a future change to any one
implementation's numeric-extraction or filtering logic cannot silently
diverge from the other two without a test catching it.

This is a single fake claim store, a single underlying dataset (issue #50
claimed, #51 free), driven through all three call sites.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import digest, github
from solomon_harness.memory_service import MemoryService


class FakeClaimStore:
    """One shared fake, used identically by all three read paths under test.

    Deterministic and IO-free (unlike the git-ref-backed ``GitClaimStore``
    every production path defaults to): given [50, 51], it always reports
    #50 as claimed by another session and #51 as free.
    """

    def filter_unclaimed(self, issue_numbers):
        return [n for n in issue_numbers if n != 50]


# The shared dataset: same two issue numbers, expressed in each read path's
# own native shape (digest/memory_service key on "github_id" strings;
# github.list_open_issues keys on an integer "number").
DIGEST_ISSUES = [
    {"github_id": "50", "title": "Taken issue", "status": "ready"},
    {"github_id": "51", "title": "Free issue", "status": "ready"},
]
GH_ISSUES = [
    {"number": 50, "title": "Taken issue"},
    {"number": 51, "title": "Free issue"},
]


class TestOpenIssuesParity(unittest.TestCase):
    """digest, memory_service, and github must agree: #50 out, #51 in."""

    def test_digest_gather_digest_agrees(self):
        class FakeDB:
            def get_latest_activity(self):
                return None

            def get_open_issues(self):
                return DIGEST_ISSUES

            def list_loop_runs(self, n):
                return []

        text = "\n".join(
            digest.gather_digest(
                ".", FakeDB(), fetch_github=False, claim_store=FakeClaimStore()
            )
        )
        self.assertIn("#51", text)
        self.assertNotIn("#50", text)

    def test_memory_service_get_open_issues_agrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "os.path.isfile",
                side_effect=lambda path: (
                    False if "config.json" in path else os.path.isfile(path)
                ),
            ):
                svc = MemoryService(
                    db_path=os.path.join(tmp, "memory.db"), claim_store=FakeClaimStore()
                )
            try:
                svc.log_issue("50", "Taken issue", "feature", "open")
                svc.log_issue("51", "Free issue", "feature", "open")
                numbers = {
                    int(issue["github_id"]) for issue in svc.get_open_issues()["issues"]
                }
            finally:
                svc.close()
        self.assertEqual(numbers, {51})

    def test_github_list_open_issues_agrees(self):
        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": True, "data": GH_ISSUES},
        ):
            res = github.list_open_issues("/tmp/workspace", claim_store=FakeClaimStore())
        self.assertTrue(res["ok"])
        numbers = {issue["number"] for issue in res["issues"]}
        self.assertEqual(numbers, {51})

    def test_all_three_paths_produce_the_same_final_set(self):
        """The actual guardrail: run all three against the same FakeClaimStore
        and the same underlying issue #50/#51 dataset, and assert they land
        on the identical filtered set. This is what Requirement #4 asks for
        -- not three isolated assertions, but one test that would fail the
        moment any one implementation's filtering diverges from the others.
        """
        store = FakeClaimStore()

        class FakeDB:
            def get_latest_activity(self):
                return None

            def get_open_issues(self):
                return DIGEST_ISSUES

            def list_loop_runs(self, n):
                return []

        digest_lines = digest.gather_digest(
            ".", FakeDB(), fetch_github=False, claim_store=store
        )
        digest_text = "\n".join(digest_lines)
        digest_numbers = {n for n in (50, 51) if f"#{n}" in digest_text}

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "os.path.isfile",
                side_effect=lambda path: (
                    False if "config.json" in path else os.path.isfile(path)
                ),
            ):
                svc = MemoryService(db_path=os.path.join(tmp, "memory.db"), claim_store=store)
            try:
                svc.log_issue("50", "Taken issue", "feature", "open")
                svc.log_issue("51", "Free issue", "feature", "open")
                service_numbers = {
                    int(issue["github_id"]) for issue in svc.get_open_issues()["issues"]
                }
            finally:
                svc.close()

        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": True, "data": GH_ISSUES},
        ):
            gh_res = github.list_open_issues("/tmp/workspace", claim_store=store)
        gh_numbers = {issue["number"] for issue in gh_res["issues"]}

        expected = {51}
        self.assertEqual(digest_numbers, expected)
        self.assertEqual(service_numbers, expected)
        self.assertEqual(gh_numbers, expected)
        self.assertEqual(digest_numbers, service_numbers)
        self.assertEqual(service_numbers, gh_numbers)


if __name__ == "__main__":
    unittest.main()
