import json
import os
import shutil
import subprocess
import tempfile
import unittest

from solomon_harness.subprocess_env import clean_git_env


class TestBootstrapAgent(unittest.TestCase):
    def setUp(self):
        # Resolve real workspace root dynamically
        self.real_workspace_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        # Create a temporary directory for isolation
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = self.test_dir.name

        # Copy required package, agents, and scripts to the test workspace
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "solomon_harness"),
            os.path.join(self.workspace_dir, "solomon_harness"),
        )
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "agents"),
            os.path.join(self.workspace_dir, "agents"),
        )
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "scripts"),
            os.path.join(self.workspace_dir, "scripts"),
        )

        # Initialize a dummy git repository in the temporary workspace
        # to satisfy git command dependencies in the bootstrap script.
        subprocess.run(["git", "init"], cwd=self.workspace_dir, capture_output=True, env=clean_git_env())
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/dummy/repo.git",
            ],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )
        with open(os.path.join(self.workspace_dir, "README.md"), "w") as f:
            f.write("# Dummy project")
        subprocess.run(
            ["git", "add", "README.md"], cwd=self.workspace_dir, capture_output=True, env=clean_git_env()
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )

        # Setup paths inside the sandboxed directory
        self.config_dir = os.path.join(self.workspace_dir, ".agent")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.script_path = os.path.join(
            self.workspace_dir, "scripts", "bootstrap-agent.sh"
        )

        # Write a clean, known starting configuration to test preservation
        self.test_initial_config = {
            "models": {
                "default": "test-default-model",
                "reasoning": "test-reasoning-model",
                "embedding": "test-embedding-model",
            },
            "timeout_seconds": 99,
            "max_retries": 5,
            "database": {"provider": "sqlite", "url": "test.db"},
        }
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.test_initial_config, f, indent=2)

        # Sandbox the shared harness home so init never writes to the real
        # ~/.solomon-harness during the test run.
        self._home = tempfile.mkdtemp()
        self._prev_home = os.environ.get("SOLOMON_HARNESS_HOME")
        os.environ["SOLOMON_HARNESS_HOME"] = self._home
        
        self._prev_skip_gh = os.environ.get("SOLOMON_SKIP_GH_CHECK")
        os.environ["SOLOMON_SKIP_GH_CHECK"] = "true"

    def tearDown(self):
        # Clean up temporary directory
        self.test_dir.cleanup()
        if self._prev_home is None:
            os.environ.pop("SOLOMON_HARNESS_HOME", None)
        else:
            os.environ["SOLOMON_HARNESS_HOME"] = self._prev_home
            
        if self._prev_skip_gh is None:
            os.environ.pop("SOLOMON_SKIP_GH_CHECK", None)
        else:
            os.environ["SOLOMON_SKIP_GH_CHECK"] = self._prev_skip_gh
        shutil.rmtree(self._home, ignore_errors=True)

    def test_non_interactive_default_via_env(self):
        env = clean_git_env(self.workspace_dir)
        env["NON_INTERACTIVE"] = "true"

        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)


        # Check preserved initial configuration
        self.assertEqual(config.get("timeout_seconds"), 99)
        self.assertEqual(config.get("max_retries"), 5)
        self.assertEqual(config.get("models", {}).get("default"), "test-default-model")
        self.assertEqual(config.get("database", {}).get("provider"), "sqlite")

    def test_non_interactive_default_via_flag(self):
        result = subprocess.run(
            ["bash", self.script_path, "--non-interactive"],
            cwd=self.workspace_dir,
            capture_output=True,
            text=True,
            env=clean_git_env(self.workspace_dir),
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.assertIn("database", config)

    def test_bootstrap_creates_fallback_kanban_and_wiki_when_no_github(self):
        # Remove git repository settings to simulate no git / no github remote
        import shutil
        shutil.rmtree(os.path.join(self.workspace_dir, ".git"), ignore_errors=True)

        env = clean_git_env(self.workspace_dir)
        env["NON_INTERACTIVE"] = "true"

        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        # Check local KANBAN.md creation
        kanban_path = os.path.join(self.workspace_dir, "planning", "KANBAN.md")
        self.assertTrue(os.path.isfile(kanban_path))
        with open(kanban_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Kanban Board", content)

        # Check local Wiki pages creation
        wiki_dir = os.path.join(self.workspace_dir, "docs", "wiki")
        self.assertTrue(os.path.isdir(wiki_dir))
        self.assertTrue(os.path.isfile(os.path.join(wiki_dir, "Home.md")))
        self.assertTrue(os.path.isfile(os.path.join(wiki_dir, "Business-Requirements.md")))
        self.assertTrue(os.path.isfile(os.path.join(wiki_dir, "Technical-Documentation.md")))

    def test_bootstrap_gemini_settings_creation_and_merge(self):
        from solomon_harness.bootstrap import bootstrap_project

        # Run bootstrap_project directly
        bootstrap_project(self.workspace_dir, non_interactive=True)
        
        # Verify .gemini/settings.json exists and has the correct hooks
        gemini_settings_path = os.path.join(self.workspace_dir, ".gemini", "settings.json")
        self.assertTrue(os.path.isfile(gemini_settings_path))
        with open(gemini_settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        
        self.assertIn("hooks", settings)
        self.assertIn("SessionStart", settings["hooks"])
        self.assertIn("PreToolUse", settings["hooks"])
        
        # Verify permissions
        self.assertIn("permissions", settings)
        self.assertIn("command(git)", settings["permissions"]["allow"])

        # Now, modify the file: remove PreToolUse to force merge PreToolUse
        settings["permissions"]["allow"].append("command(dummy)")
        settings["hooks"].pop("PreToolUse")
        with open(gemini_settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            
        # Run bootstrap_project again (covers merge PreToolUse)
        bootstrap_project(self.workspace_dir, non_interactive=True)
        
        with open(gemini_settings_path, "r", encoding="utf-8") as f:
            settings_merged = json.load(f)
        self.assertIn("PreToolUse", settings_merged["hooks"])
        self.assertIn("command(dummy)", settings_merged["permissions"]["allow"])

        # Modify the file: remove SessionStart to force merge SessionStart
        settings_merged["hooks"].pop("SessionStart")
        with open(gemini_settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_merged, f, indent=2)

        # Run bootstrap_project again (covers merge SessionStart)
        bootstrap_project(self.workspace_dir, non_interactive=True)

        with open(gemini_settings_path, "r", encoding="utf-8") as f:
            settings_merged2 = json.load(f)
        self.assertIn("SessionStart", settings_merged2["hooks"])

        # Run bootstrap_project again with no changes (covers 578: updated is False)
        bootstrap_project(self.workspace_dir, non_interactive=True)

        # Write invalid/malformed JSON to test error handling (covers 543-544)
        with open(gemini_settings_path, "w", encoding="utf-8") as f:
            f.write("{invalid_json")

        # Run bootstrap_project again (covers exception handling)
        bootstrap_project(self.workspace_dir, non_interactive=True)
        
        with open(gemini_settings_path, "r", encoding="utf-8") as f:
            settings_recovered = json.load(f)
        self.assertIn("hooks", settings_recovered)

        # Trigger general read exception to cover lines 556-558
        from unittest.mock import patch
        import builtins
        real_open = builtins.open
        def mock_open_fn(file, *args, **kwargs):
            if str(file).endswith(os.path.join(".gemini", "settings.json")):
                mode = args[0] if args else kwargs.get("mode", "r")
                if "w" not in mode:
                    raise PermissionError("no read access")
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            # Run bootstrap_project again; it should log warning and return early without raising
            bootstrap_project(self.workspace_dir, non_interactive=True)


class TestProjectIdentityNotClobberedByHarnessInstall(unittest.TestCase):
    """A fresh project with no pyproject.toml/package.json of its own must keep
    its own directory name as its identity. Regression: _install_harness_files
    copies this repo's own pyproject.toml (name = "solomon-harness") into any
    workspace that lacks one, so reading project metadata after that copy
    misidentified every from-scratch install as "solomon-harness"."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = os.path.join(self.test_dir.name, "acme-trader")
        os.makedirs(self.workspace_dir)

        subprocess.run(["git", "init"], cwd=self.workspace_dir, capture_output=True, env=clean_git_env())
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.workspace_dir,
            capture_output=True,
            env=clean_git_env(),
        )

        self._home = tempfile.mkdtemp()
        self._prev_home = os.environ.get("SOLOMON_HARNESS_HOME")
        os.environ["SOLOMON_HARNESS_HOME"] = self._home

        self._prev_skip_gh = os.environ.get("SOLOMON_SKIP_GH_CHECK")
        os.environ["SOLOMON_SKIP_GH_CHECK"] = "true"

    def tearDown(self):
        self.test_dir.cleanup()
        if self._prev_home is None:
            os.environ.pop("SOLOMON_HARNESS_HOME", None)
        else:
            os.environ["SOLOMON_HARNESS_HOME"] = self._prev_home

        if self._prev_skip_gh is None:
            os.environ.pop("SOLOMON_SKIP_GH_CHECK", None)
        else:
            os.environ["SOLOMON_SKIP_GH_CHECK"] = self._prev_skip_gh
        shutil.rmtree(self._home, ignore_errors=True)

    def test_fresh_project_keeps_its_own_name_not_the_harness_own(self):
        from solomon_harness.bootstrap import bootstrap_project

        bootstrap_project(self.workspace_dir, non_interactive=True)

        # The harness's own pyproject.toml is installed since none existed --
        # confirms the copy happened, so the assertion below is meaningful.
        self.assertTrue(os.path.isfile(os.path.join(self.workspace_dir, "pyproject.toml")))

        kanban_path = os.path.join(self.workspace_dir, "planning", "KANBAN.md")
        self.assertTrue(os.path.isfile(kanban_path))
        with open(kanban_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("acme-trader", content)
        self.assertNotIn("solomon-harness", content)


class TestGithubPrereqStatus(unittest.TestCase):
    """Wiki is only a hard requirement for public repos; GitHub Projects always
    blocks init, since the delivery board depends on it."""

    def test_public_repo_missing_wiki_blocks(self):
        from solomon_harness.bootstrap import github_prereq_status

        wiki_ok, wiki_blocking, blocked = github_prereq_status(
            wiki_enabled=False, wiki_initialized=False, projects_ok=True, is_public=True
        )
        self.assertFalse(wiki_ok)
        self.assertTrue(wiki_blocking)
        self.assertTrue(blocked)

    def test_private_repo_missing_wiki_does_not_block(self):
        from solomon_harness.bootstrap import github_prereq_status

        wiki_ok, wiki_blocking, blocked = github_prereq_status(
            wiki_enabled=False, wiki_initialized=False, projects_ok=True, is_public=False
        )
        self.assertFalse(wiki_ok)
        self.assertFalse(wiki_blocking)
        self.assertFalse(blocked)

    def test_private_repo_missing_projects_still_blocks(self):
        from solomon_harness.bootstrap import github_prereq_status

        wiki_ok, wiki_blocking, blocked = github_prereq_status(
            wiki_enabled=False, wiki_initialized=False, projects_ok=False, is_public=False
        )
        self.assertFalse(wiki_blocking)
        self.assertTrue(blocked)

    def test_public_repo_with_wiki_and_projects_does_not_block(self):
        from solomon_harness.bootstrap import github_prereq_status

        wiki_ok, wiki_blocking, blocked = github_prereq_status(
            wiki_enabled=True, wiki_initialized=True, projects_ok=True, is_public=True
        )
        self.assertTrue(wiki_ok)
        self.assertFalse(wiki_blocking)
        self.assertFalse(blocked)


class TestHasGithubProjectAndWiki(unittest.TestCase):
    """The local-Kanban-fallback check: wiki is only required alongside the
    project board for public repos."""

    def _fake_gh_output(self, has_projects, has_wiki, is_private):
        return json.dumps(
            {
                "hasProjectsEnabled": has_projects,
                "hasWikiEnabled": has_wiki,
                "isPrivate": is_private,
            }
        )

    def test_private_repo_with_projects_no_wiki_counts_as_ready(self):
        from unittest.mock import patch

        from solomon_harness.bootstrap import has_github_project_and_wiki

        with patch(
            "subprocess.check_output",
            return_value=self._fake_gh_output(True, False, True),
        ):
            self.assertTrue(has_github_project_and_wiki("/ws", "git@github.com:o/r.git"))

    def test_public_repo_with_projects_no_wiki_is_not_ready(self):
        from unittest.mock import patch

        from solomon_harness.bootstrap import has_github_project_and_wiki

        with patch(
            "subprocess.check_output",
            return_value=self._fake_gh_output(True, False, False),
        ):
            self.assertFalse(has_github_project_and_wiki("/ws", "git@github.com:o/r.git"))

    def test_no_projects_board_is_never_ready(self):
        from unittest.mock import patch

        from solomon_harness.bootstrap import has_github_project_and_wiki

        with patch(
            "subprocess.check_output",
            return_value=self._fake_gh_output(False, True, True),
        ):
            self.assertFalse(has_github_project_and_wiki("/ws", "git@github.com:o/r.git"))


class TestInitWikiHint(unittest.TestCase):
    """The init flow detects an uninitialized GitHub wiki and only hints; it must
    never bootstrap it, since init commonly runs non-interactive."""

    def test_init_hints_on_zero_refs_and_never_bootstraps(self):
        import contextlib
        import io

        from solomon_harness.bootstrap import hint_uninitialized_wiki

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = hint_uninitialized_wiki(
                "/ws",
                "git@github.com:o/r.git",
                wiki_enabled_checker=lambda _ws: True,
                refs_checker=lambda url, timeout=10.0: False,
            )
        out = buf.getvalue()

        # Detect-and-hint: it names the manual web step and returns nothing. There
        # is no bootstrapper parameter or browser path, so it cannot bootstrap.
        self.assertIsNone(result)
        self.assertIn("https://github.com/o/r/wiki/_new", out)


if __name__ == "__main__":
    unittest.main()


class TestInstallDocsBoundary(unittest.TestCase):
    """The harness's own documents never travel into installed projects
    (maintainer directive, #234 review round): an install receives only the
    operating docs the commands read and the convention scaffolding, and each
    project's record trees start empty."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_ships_skeleton_docs_without_harness_records(self):
        from solomon_harness import bootstrap

        bootstrap._install_harness_files(self.workspace)

        adrs = os.path.join(self.workspace, "docs", "adrs")
        specs = os.path.join(self.workspace, "docs", "specs")
        self.assertEqual(
            sorted(os.listdir(adrs)), ["0000-adr-template.md", "README.md"],
            "an installed project's docs/adrs holds only the convention scaffolding",
        )
        self.assertEqual(
            sorted(os.listdir(specs)), ["0000-spec-template.md", "README.md"],
            "an installed project's docs/specs holds only the convention scaffolding",
        )
        # The harness's own wiki pages and root README stay home.
        self.assertFalse(os.path.isdir(os.path.join(self.workspace, "docs", "wiki")))
        self.assertFalse(os.path.isfile(os.path.join(self.workspace, "README.md")))
        # The operating documents the commands read do travel.
        self.assertTrue(
            os.path.isfile(os.path.join(self.workspace, "docs", "solomon-workflow.md"))
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.workspace, "docs", "templates"))
        )
