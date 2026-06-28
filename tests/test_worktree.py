import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest

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
