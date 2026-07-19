"""Guard for issue #114.

`/solomon-review` must take an approved PR out of draft (`gh pr ready`). The
host-neutral workflow catalog is the behavioral source consumed by every host;
the Claude command is only a metadata bridge to it.

These tests assert the *actionable* instruction (`gh pr ready <args>`) is present
in the source and that the Claude bridge points to it. They anchor the check to
the operative command, not prose that merely mentions `gh pr ready`, so a partial
edit that drops the run-line cannot pass.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_MD = os.path.join(
    REPO_ROOT,
    "solomon_harness",
    "catalog",
    "workflows",
    "solomon-review.md",
)
REVIEW_BRIDGE = os.path.join(REPO_ROOT, ".claude", "commands", "solomon-review.md")


class TestReviewMarksReady(unittest.TestCase):
    def test_command_source_requires_pr_ready_on_approval(self):
        with open(REVIEW_MD, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(
            "gh pr ready {{arguments}}",
            body,
            "the canonical review workflow must run `gh pr ready {{arguments}}` on "
            "approval so an approved PR leaves draft (#114); the operative run-line, "
            "not just a prose mention of `gh pr ready`, must be present",
        )

    def test_claude_bridge_points_to_the_canonical_review_workflow(self):
        with open(REVIEW_BRIDGE, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(
            "solomon_harness/catalog/workflows/solomon-review.md",
            body,
            "the Claude review bridge must point to the canonical workflow",
        )


if __name__ == "__main__":
    unittest.main()
