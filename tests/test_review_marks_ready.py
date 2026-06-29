"""Guard for issue #114.

`/solomon-review` must take an approved PR out of draft (`gh pr ready`). The
review command file (`.claude/commands/solomon-review.md`) is the single
behavioral source for both Claude Code and the headless Gemini engine
(`workflows.build_prompt` reads it directly), and `.gemini/commands/
solomon-review.toml` is generated from it by `cli compile`.

These tests assert the *actionable* instruction (`gh pr ready <args>`) is present
in the source and in the regenerated mirror — anchored to the operative command,
not the prose that merely mentions `gh pr ready`, so a partial edit that drops the
run-line cannot pass. They guard the instruction text the host LLM executes; they
cannot assert the runtime call itself, which is the inherent ceiling for a
prompt artifact.
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
            "gh pr ready $ARGUMENTS",
            body,
            "the /solomon-review command must run `gh pr ready $ARGUMENTS` on "
            "approval so an approved PR leaves draft (#114); the operative run-line, "
            "not just a prose mention of `gh pr ready`, must be present",
        )

    def test_gemini_mirror_carries_the_rule(self):
        if not os.path.isfile(REVIEW_TOML):
            self.skipTest("Gemini mirror not generated in this workspace")
        with open(REVIEW_TOML, encoding="utf-8") as fh:
            body = fh.read()
        # generate-integrations.py rewrites $ARGUMENTS -> {{args}} in the mirror.
        self.assertIn(
            "gh pr ready {{args}}",
            body,
            "the regenerated Gemini command mirror is stale or missing the run-line; "
            "run `cli compile` after editing the review command",
        )


if __name__ == "__main__":
    unittest.main()
