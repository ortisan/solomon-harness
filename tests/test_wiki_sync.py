"""Behavioural tests for the no-browser floor of scripts/wiki-sync.sh (issue #117).

These drive the real script through a subprocess against local bare repositories
(refs present / 0 refs) or a git PATH shim (timeout), mirroring the subprocess
style of tests/test_bootstrap.py. They assert the observable contract of the
degrade floor: an uninitialized or undetectable GitHub wiki ends in a
deterministic exit 4 with an actionable message and no raw git stderr, while an
initialized wiki syncs unchanged and exits 0.
"""

import os
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_SYNC_SRC = os.path.join(REPO_ROOT, "scripts", "wiki-sync.sh")

# Git exports these while a hook runs; left in the child environment they point
# "git" at the repo under test instead of each fixture's throwaway repo (the
# test-isolation leak fixed for the suite in #41). Strip them per fixture run.
_GIT_LEAK_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def _git(args, cwd):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


class WikiSyncFixture(unittest.TestCase):
    """A throwaway workspace whose scripts/wiki-sync.sh runs against a local wiki."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

        os.makedirs(os.path.join(self.root, "scripts"))
        shutil.copy(WIKI_SYNC_SRC, os.path.join(self.root, "scripts", "wiki-sync.sh"))

        # docs/wiki must carry at least one markdown file or the script exits early.
        wiki_src = os.path.join(self.root, "docs", "wiki")
        os.makedirs(wiki_src)
        with open(os.path.join(wiki_src, "Home.md"), "w", encoding="utf-8") as f:
            f.write("# Home\n\nSeed page.\n")

        _git(["init", "-q"], self.root)
        _git(["config", "user.name", "Wiki Sync Test"], self.root)
        _git(["config", "user.email", "wiki-sync-test@example.com"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _set_wiki_remote(self, wiki_path):
        # A remote.origin.url already ending in .wiki.git maps to itself, so the
        # script's WIKI_URL resolves straight to the local repo under test.
        _git(["remote", "add", "origin", wiki_path], self.root)

    def _seed_bare_with_ref(self):
        seed = tempfile.mkdtemp()
        try:
            _git(["init", "-q"], seed)
            _git(["config", "user.name", "Seed"], seed)
            _git(["config", "user.email", "seed@example.com"], seed)
            with open(os.path.join(seed, "README.md"), "w", encoding="utf-8") as f:
                f.write("seed\n")
            _git(["add", "."], seed)
            _git(["commit", "-q", "-m", "seed"], seed)
            bare = os.path.join(self.root, "remote.wiki.git")
            subprocess.run(
                ["git", "clone", "--bare", "-q", seed, bare],
                check=True,
                capture_output=True,
                text=True,
            )
            return bare
        finally:
            shutil.rmtree(seed, ignore_errors=True)

    def _empty_bare(self):
        bare = os.path.join(self.root, "remote.wiki.git")
        subprocess.run(
            ["git", "init", "--bare", "-q", bare],
            check=True,
            capture_output=True,
            text=True,
        )
        return bare

    def _refs_on(self, bare):
        out = subprocess.run(
            ["git", "ls-remote", "--heads", bare],
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    def _run(self, extra_env=None, timeout=120):
        env = {k: v for k, v in os.environ.items() if k not in _GIT_LEAK_VARS}
        env["GIT_TERMINAL_PROMPT"] = "0"
        if extra_env:
            env.update(extra_env)
        script = os.path.join(self.root, "scripts", "wiki-sync.sh")
        return subprocess.run(
            ["bash", script],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


class TestWikiSyncDegrade(WikiSyncFixture):
    """Step 1 (DEGRADE): an uninitialized wiki must exit 4 with an actionable
    message, surface no raw clone/push stderr, and run no clone or push."""

    def test_zero_refs_degrades_with_exit_4_and_actionable_message(self):
        bare = self._empty_bare()
        self._set_wiki_remote(bare)

        result = self._run()
        out = result.stdout + result.stderr

        self.assertEqual(result.returncode, 4, out)
        self.assertIn("wiki/_new", out)
        self.assertRegex(out.lower(), r"not been initialized|never been|uninitialized")
        self.assertNotIn("Repository not found", out)
        self.assertNotIn("fatal:", out)
        # No clone or push happened: the bare wiki repo still carries 0 refs.
        self.assertEqual(self._refs_on(bare), "")

    def test_missing_wiki_repo_degrades_without_raw_git_stderr(self):
        missing = os.path.join(self.root, "absent.wiki.git")
        self._set_wiki_remote(missing)

        result = self._run()
        out = result.stdout + result.stderr

        self.assertEqual(result.returncode, 4, out)
        self.assertIn("wiki/_new", out)
        self.assertNotIn("fatal:", out)
        self.assertNotIn("does not appear to be a git repository", out)
        self.assertNotIn("Repository not found", out)


class TestWikiSyncNoOp(WikiSyncFixture):
    """Step 2 (NO-OP / IDEMPOTENCY): with >= 1 ref present the precheck falls
    through to the existing clone, copy, commit and push, exiting 0 with no
    degraded message and no first-page bootstrap."""

    def test_refs_present_syncs_unchanged_and_exits_zero(self):
        bare = self._seed_bare_with_ref()
        self._set_wiki_remote(bare)

        result = self._run()
        out = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, out)
        self.assertNotIn("wiki/_new", out)
        self.assertNotIn("has not been initialized", out)
        self.assertIn("synchronized successfully", out)

        # The docs page was published to the wiki remote: clone, commit and push
        # all ran against the initialized repo.
        tree = subprocess.run(
            ["git", "-C", bare, "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("Home.md", tree)


if __name__ == "__main__":
    unittest.main()
