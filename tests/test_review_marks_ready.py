"""Guard for issue #114.

`/solomon-review` must take an approved PR out of draft (`gh pr ready`). The
review command file (`.claude/commands/solomon-review.md`) is the single
behavioral source for both Claude Code and the headless Gemini engine
(`workflows.build_prompt` reads it directly), and `.gemini/commands/
solomon-review.toml` is generated from it by `cli compile`. These tests fail if
the draft->ready rule is dropped from the source or missing from the regenerated
mirror, so an approving review can never again leave a PR stranded in draft.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_MD = os.path.join(REPO_ROOT, ".claude", "commands", "solomon-review.md")
REVIEW_TOML = os.path.join(REPO_ROOT, ".gemini", "commands", "solomon-review.toml")


class TestReviewMarksReady(unittest.TestCase):
    def test_command_source_requires_pr_ready_on_approval(self):
        with open(REVIEW_MD, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(
            "gh pr ready",
            body,
            "the /solomon-review command must run `gh pr ready` on approval so an "
            "approved PR leaves draft (#114)",
        )

    def test_gemini_mirror_carries_the_rule(self):
        if not os.path.isfile(REVIEW_TOML):
            self.skipTest("Gemini mirror not generated in this workspace")
        with open(REVIEW_TOML, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(
            "gh pr ready",
            body,
            "the regenerated Gemini command mirror is stale; run `cli compile` "
            "after editing the review command",
        )


if __name__ == "__main__":
    unittest.main()
