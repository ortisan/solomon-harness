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
import time
import unittest
from pathlib import Path

from solomon_harness.install_layout import install_project


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

        # docs/wiki must carry at least one markdown file or the script exits early.
        wiki_src = os.path.join(self.root, "docs", "wiki")
        os.makedirs(wiki_src)
        with open(os.path.join(wiki_src, "Home.md"), "w", encoding="utf-8") as f:
            f.write("# Home\n\nSeed page.\n")

        _git(["init", "-q"], self.root)
        _git(["config", "user.name", "Wiki Sync Test"], self.root)
        _git(["config", "user.email", "wiki-sync-test@example.com"], self.root)
        install_project(Path(self.root), source_root=Path(REPO_ROOT))

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

    def _install_git_shim_sleeping_on(self, subcommand, seconds=30):
        # A git PATH shim that hangs on one subcommand and delegates everything
        # else to the real git, so the script's own git calls still work while the
        # ls-remote probe stalls. Used to drive the detection-timeout path.
        real_git = shutil.which("git")
        shim_dir = os.path.join(self.root, "binshim")
        os.makedirs(shim_dir, exist_ok=True)
        shim = os.path.join(shim_dir, "git")
        with open(shim, "w", encoding="utf-8") as f:
            f.write(
                "#!/bin/sh\n"
                f'if [ "$1" = "{subcommand}" ]; then\n'
                f"  sleep {seconds}\n"
                "  exit 0\n"
                "fi\n"
                f'exec "{real_git}" "$@"\n'
            )
        os.chmod(shim, 0o755)
        return shim_dir

    def _run(self, extra_env=None, timeout=120):
        env = {k: v for k, v in os.environ.items() if k not in _GIT_LEAK_VARS}
        env["GIT_TERMINAL_PROMPT"] = "0"
        if extra_env:
            env.update(extra_env)
        script = os.path.join(
            self.root, ".agents", "solomon", "scripts", "wiki-sync.sh"
        )
        return subprocess.run(
            ["bash", script],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


class TestWikiSyncSourceLayout(unittest.TestCase):
    def test_source_script_uses_isolated_runtime_and_canonical_state_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy(Path(REPO_ROOT) / "scripts" / "wiki-sync.sh", scripts)
            wiki = root / "docs" / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "Home.md").write_text("# Source wiki\n", encoding="utf-8")
            _git(["init", "-q"], root)
            bare = root / "remote.wiki.git"
            _git(["init", "--bare", "-q", str(bare)], root)
            _git(["remote", "add", "origin", str(bare)], root)

            capture = root / "uv-invocation"
            shim_directory = root / "bin"
            shim_directory.mkdir()
            shim = shim_directory / "uv"
            shim.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "{\n"
                "  printf 'cwd=%s\\n' \"$PWD\"\n"
                "  printf 'venv=%s\\n' \"$UV_PROJECT_ENVIRONMENT\"\n"
                "  printf 'pythonpath=%s\\n' \"${PYTHONPATH-unset}\"\n"
                "  printf 'pythonhome=%s\\n' \"${PYTHONHOME-unset}\"\n"
                "  printf '%s\\n' \"$@\"\n"
                "} > \"$WIKI_UV_CAPTURE\"\n"
                "exit 4\n",
                encoding="utf-8",
            )
            shim.chmod(0o755)
            env = {key: value for key, value in os.environ.items() if key not in _GIT_LEAK_VARS}
            env.update(
                {
                    "PATH": str(shim_directory) + os.pathsep + env["PATH"],
                    "PYTHONHOME": str(root / "untrusted-home"),
                    "PYTHONPATH": str(root / "untrusted-path"),
                    "WIKI_UV_CAPTURE": str(capture),
                }
            )

            result = subprocess.run(
                ["bash", str(scripts / "wiki-sync.sh")],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            lines = capture.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], f"cwd={root}")
            self.assertEqual(
                lines[1],
                f"venv={root / '.agents' / 'solomon' / 'state' / 'venv'}",
            )
            self.assertEqual(lines[2:4], ["pythonpath=unset", "pythonhome=unset"])
            self.assertEqual(
                lines[4:],
                [
                    "run",
                    "--frozen",
                    "--project",
                    str(root),
                    "python",
                    "-I",
                    "-m",
                    "solomon_harness.wiki_bootstrap",
                    "detect",
                    str(bare),
                ],
            )


class TestWikiSyncInstalledLayout(unittest.TestCase):
    def test_installed_script_anchors_project_data_at_the_consumer_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(["init", "-q"], root)
            wiki = root / "docs" / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "Home.md").write_text("# Consumer wiki\n", encoding="utf-8")
            install_project(root, source_root=Path(REPO_ROOT))
            script = root / ".agents" / "solomon" / "scripts" / "wiki-sync.sh"
            env = {key: value for key, value in os.environ.items() if key not in _GIT_LEAK_VARS}
            env["PYTHONPATH"] = str(root)

            result = subprocess.run(
                ["bash", str(script)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            copied = root / "tmp" / "wiki-mock-verification" / "Home.md"
            self.assertEqual(copied.read_text(encoding="utf-8"), "# Consumer wiki\n")
            self.assertFalse((root / ".agents" / "solomon" / "tmp").exists())


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

    def test_detection_ignores_consumer_python_shadow_packages_and_sitecustomize(self):
        bare = self._empty_bare()
        self._set_wiki_remote(bare)
        sentinel = Path(self.root) / "python-shadow-executed"
        shadow_package = Path(self.root) / "solomon_harness"
        shadow_package.mkdir()
        (shadow_package / "__init__.py").write_text("", encoding="utf-8")
        (shadow_package / "wiki_bootstrap.py").write_text(
            "from pathlib import Path\n"
            "import os\n"
            "Path(os.environ['WIKI_SHADOW_SENTINEL']).write_text('module')\n"
            "raise SystemExit(4)\n",
            encoding="utf-8",
        )
        (Path(self.root) / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            "import os\n"
            "Path(os.environ['WIKI_SHADOW_SENTINEL']).write_text('sitecustomize')\n",
            encoding="utf-8",
        )

        result = self._run(
            extra_env={
                "PYTHONPATH": self.root + os.pathsep + REPO_ROOT,
                "WIKI_SHADOW_SENTINEL": str(sentinel),
            }
        )

        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertFalse(
            sentinel.exists(),
            sentinel.read_text(encoding="utf-8") if sentinel.exists() else "",
        )


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


class TestWikiSyncDetectionTimeout(WikiSyncFixture):
    """Step 3 (DETECTION TIMEOUT): when ls-remote does not return within the
    timeout the script exits 4 within roughly that bound, reports detection as
    inconclusive, names the same manual step, and surfaces no raw git error."""

    def test_ls_remote_hang_exits_4_within_bound_with_inconclusive_message(self):
        # Point at a plausible wiki URL; the shim makes ls-remote hang regardless.
        self._set_wiki_remote(os.path.join(self.root, "remote.wiki.git"))
        shim_dir = self._install_git_shim_sleeping_on("ls-remote", seconds=30)
        env = {
            "PATH": shim_dir + os.pathsep + os.environ["PATH"],
            "WIKI_SYNC_LSREMOTE_TIMEOUT": "2",
        }

        started = time.monotonic()
        result = self._run(extra_env=env)
        elapsed = time.monotonic() - started
        out = result.stdout + result.stderr

        self.assertEqual(result.returncode, 4, out)
        self.assertLess(elapsed, 15, f"detection did not bound the hang: {elapsed:.1f}s")
        self.assertIn("inconclusive", out.lower())
        self.assertIn("wiki/_new", out)
        self.assertNotIn("fatal:", out)
        self.assertNotIn("has not been initialized", out)


if __name__ == "__main__":
    unittest.main()
