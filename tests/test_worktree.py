import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from solomon_harness import worktree


def _clean_env():
    # Drop the GIT_* redirectors a surrounding git hook would set, so these tests
    # target their own temp repos instead of the repo being committed.
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            env.pop(key, None)
    return env


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, *args],
        check=True,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )


def _worktree_count(repo):
    out = _git(repo, "worktree", "list").stdout
    return len([ln for ln in out.splitlines() if ln.strip()])


class WorktreeTestBase(unittest.TestCase):
    def setUp(self):
        # A private parent so the sibling "<name>-worktrees/" root is isolated.
        self.parent = tempfile.mkdtemp(prefix="sh-wt-")
        self.repo = os.path.join(self.parent, "proj")
        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "checkout", "-q", "-b", "develop")
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as f:
            f.write("seed\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.parent, ignore_errors=True)


class TestWorktreePath(WorktreeTestBase):
    def test_path_is_sibling_root_with_dashed_branch(self):
        path = worktree.worktree_path(self.repo, "feature/add-csv-export")
        self.assertEqual(os.path.basename(path), "feature-add-csv-export")
        self.assertEqual(os.path.basename(os.path.dirname(path)), "proj-worktrees")
        # The root sits beside the repo, not inside it.
        self.assertEqual(
            os.path.dirname(os.path.dirname(path)), os.path.realpath(self.parent)
        )
        self.assertFalse(path.startswith(os.path.realpath(self.repo) + os.sep))

    def test_invalid_branch_rejected(self):
        for bad in ["", "-x", "a..b", "feature/..", "a b", "x;rm -rf /", "/abs"]:
            with self.assertRaises(worktree.WorktreeError):
                worktree.worktree_path(self.repo, bad)

    def test_control_characters_rejected(self):
        # A trailing newline slips past a "$"-anchored regex; fullmatch must reject it.
        for bad in ["feature/x\n", "feature\tx", "feature/x\r"]:
            with self.assertRaises(worktree.WorktreeError):
                worktree.worktree_path(self.repo, bad)


class TestEnsureWorktree(WorktreeTestBase):
    def test_creates_worktree_on_branch_from_base(self):
        path = worktree.ensure_worktree(self.repo, "feature/x", base="develop")
        self.assertTrue(os.path.isdir(path))
        porcelain = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertIn("branch refs/heads/feature/x", porcelain)
        # The primary checkout is untouched.
        head = _git(self.repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.assertEqual(head, "develop")

    def test_succeeds_when_primary_checkout_is_dirty(self):
        with open(os.path.join(self.repo, "README.md"), "a", encoding="utf-8") as f:
            f.write("uncommitted\n")
        path = worktree.ensure_worktree(self.repo, "feature/y", base="develop")
        self.assertTrue(os.path.isdir(path))
        with open(os.path.join(self.repo, "README.md"), encoding="utf-8") as f:
            self.assertIn("uncommitted", f.read())

    def test_idempotent_reuse_runs_no_second_add(self):
        first = worktree.ensure_worktree(self.repo, "feature/z", base="develop")
        count = _worktree_count(self.repo)
        second = worktree.ensure_worktree(self.repo, "feature/z", base="develop")
        self.assertEqual(first, second)
        self.assertEqual(count, _worktree_count(self.repo))

    def test_conflict_when_path_occupied_by_non_worktree(self):
        target = worktree.worktree_path(self.repo, "feature/occupied")
        os.makedirs(target)
        with open(os.path.join(target, "stray.txt"), "w", encoding="utf-8") as f:
            f.write("not a worktree\n")
        before = _worktree_count(self.repo)
        with self.assertRaises(worktree.WorktreeConflict):
            worktree.ensure_worktree(self.repo, "feature/occupied", base="develop")
        self.assertEqual(before, _worktree_count(self.repo))

    def test_conflict_when_branch_checked_out_elsewhere(self):
        other = os.path.join(self.parent, "other-location")
        _git(self.repo, "worktree", "add", "-b", "feature/dup", other, "develop")
        with self.assertRaises(worktree.WorktreeConflict):
            worktree.ensure_worktree(self.repo, "feature/dup", base="develop")

    def test_option_shaped_base_rejected(self):
        # base="--force" must not be parsed as a git flag (it would defeat the
        # conflict checks); validation rejects it before it reaches git.
        with self.assertRaises(worktree.WorktreeError):
            worktree.ensure_worktree(self.repo, "feature/badbase", base="--force")

    def test_worktree_built_at_the_requested_base_commit(self):
        # Branch "release" stays at the seed commit; develop advances past it.
        _git(self.repo, "branch", "release", "develop")
        with open(os.path.join(self.repo, "EXTRA.txt"), "w", encoding="utf-8") as f:
            f.write("develop only\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "advance develop")
        release_sha = _git(self.repo, "rev-parse", "release").stdout.strip()
        path = worktree.ensure_worktree(self.repo, "feature/frombase", base="release")
        self.assertEqual(_git(path, "rev-parse", "HEAD").stdout.strip(), release_sha)

    def test_reuses_existing_branch_after_worktree_removed(self):
        first = worktree.ensure_worktree(self.repo, "feature/readd", base="develop")
        _git(self.repo, "worktree", "remove", first)
        # The branch still exists, the worktree dir is gone: re-add without -b.
        again = worktree.ensure_worktree(self.repo, "feature/readd", base="develop")
        self.assertEqual(first, again)
        self.assertTrue(os.path.isdir(again))
        porcelain = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertIn("branch refs/heads/feature/readd", porcelain)


class TestGitEnvIsolation(WorktreeTestBase):
    def test_ignores_leaked_git_redirectors(self):
        # Build a second, unrelated repo whose GIT_* would hijack "git -C" if the
        # helper did not strip the redirectors (the condition the env-scrub exists
        # for, e.g. running inside a git hook).
        other = os.path.join(self.parent, "other-repo")
        os.makedirs(other)
        _git(other, "init", "-q")
        _git(other, "config", "user.email", "o@example.com")
        _git(other, "config", "user.name", "Other")
        _git(other, "checkout", "-q", "-b", "develop")
        with open(os.path.join(other, "f.txt"), "w", encoding="utf-8") as f:
            f.write("other\n")
        _git(other, "add", "-A")
        _git(other, "commit", "-q", "-m", "other init")

        leaked = {
            "GIT_DIR": os.path.join(other, ".git"),
            "GIT_WORK_TREE": other,
            "GIT_INDEX_FILE": os.path.join(other, ".git", "index"),
        }
        with mock.patch.dict(os.environ, leaked):
            path = worktree.ensure_worktree(self.repo, "feature/isolated", base="develop")

        # The worktree must be registered in self.repo, not the leaked "other" repo.
        registered = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertIn(os.path.realpath(path), registered)
        other_list = _git(other, "worktree", "list", "--porcelain").stdout
        self.assertNotIn("feature/isolated", other_list)


class TestCliWorktree(WorktreeTestBase):
    def test_prints_path_and_returns_zero(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = worktree.cli_worktree(self.repo, "feature/cli", base="develop")
        self.assertEqual(rc, 0)
        printed = buf.getvalue().strip()
        self.assertTrue(os.path.isdir(printed))

    def test_conflict_returns_nonzero_and_writes_stderr(self):
        target = worktree.worktree_path(self.repo, "feature/clic")
        os.makedirs(target)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = worktree.cli_worktree(self.repo, "feature/clic", base="develop")
        self.assertEqual(rc, 1)
        self.assertIn("Error", err.getvalue())


class TestCliMainWiring(WorktreeTestBase):
    def test_worktree_subcommand_prints_path_and_exits_zero(self):
        from solomon_harness import cli

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(buf):
            cli.main(
                harness_dir=self.repo,
                argv=["worktree", "feature/wire", "--base", "develop"],
            )
        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(os.path.isdir(buf.getvalue().strip()))


if __name__ == "__main__":
    unittest.main()
