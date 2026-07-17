import os
import unittest
from unittest.mock import patch

from solomon_harness.subprocess_env import clean_gh_env, clean_git_env


class TestCleanGitEnv(unittest.TestCase):
    def test_strips_every_git_prefixed_variable(self):
        leaked = {
            "GIT_DIR": "/tmp/leaked/.git",
            "GIT_WORK_TREE": "/tmp/leaked",
            "GIT_INDEX_FILE": "/tmp/leaked/index",
            "GIT_PREFIX": "x/",
            "GIT_COMMON_DIR": "/tmp/leaked/.git",
            "GIT_OBJECT_DIRECTORY": "/tmp/leaked/.git/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/leaked/.git/objects2",
            "GIT_AUTHOR_NAME": "someone",  # not on the old curated allowlist either
        }
        with patch.dict(os.environ, leaked):
            env = clean_git_env()
        # Every inherited GIT_* is stripped. GIT_TERMINAL_PROMPT is the one
        # exception: it is deliberately (re)set to "0" so a stalled credential
        # prompt fails fast instead of hanging a git subprocess.
        self.assertFalse(any(k.startswith("GIT_") for k in env if k != "GIT_TERMINAL_PROMPT"))
        self.assertEqual(env.get("GIT_TERMINAL_PROMPT"), "0")

    def test_preserves_non_git_variables(self):
        with patch.dict(os.environ, {"PATH": os.environ.get("PATH", ""), "SOME_OTHER_VAR": "keep-me"}):
            env = clean_git_env()
        self.assertEqual(env.get("SOME_OTHER_VAR"), "keep-me")
        self.assertIn("PATH", env)


class TestCleanGhEnv(unittest.TestCase):
    def test_strips_repository_override_and_git_context(self):
        leaked = {
            "GH_REPO": "attacker/other",
            "GIT_DIR": "/tmp/leaked/.git",
            "PATH": os.environ.get("PATH", ""),
        }
        with patch.dict(os.environ, leaked):
            env = clean_gh_env()

        self.assertNotIn("GH_REPO", env)
        self.assertNotIn("GIT_DIR", env)
        self.assertIn("PATH", env)


if __name__ == "__main__":
    unittest.main()
