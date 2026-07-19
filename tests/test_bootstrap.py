import json
import os
import shutil
import subprocess
import tempfile
import unittest


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
        subprocess.run(["git", "init"], cwd=self.workspace_dir, capture_output=True)
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
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.workspace_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.workspace_dir,
            capture_output=True,
        )
        with open(os.path.join(self.workspace_dir, "README.md"), "w") as f:
            f.write("# Dummy project")
        subprocess.run(
            ["git", "add", "README.md"], cwd=self.workspace_dir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.workspace_dir,
            capture_output=True,
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

        # Force unreachable SurrealDB URL so database_client falls back to local sqlite
        self._prev_surreal_url = os.environ.get("SURREAL_URL")
        self._prev_surreal_user = os.environ.get("SURREAL_USER")
        self._prev_surreal_pass = os.environ.get("SURREAL_PASS")
        os.environ["SURREAL_URL"] = "ws://127.0.0.1:1/rpc"
        os.environ["SURREAL_USER"] = ""
        os.environ["SURREAL_PASS"] = ""

        # Create a mock 'gh' executable to prevent any real network calls
        self.mock_bin_dir = tempfile.mkdtemp()
        gh_path = os.path.join(self.mock_bin_dir, "gh")
        with open(gh_path, "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(gh_path, 0o755)
        
        self._prev_path = os.environ.get("PATH")
        os.environ["PATH"] = f"{self.mock_bin_dir}:{self._prev_path or ''}"

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

        # Clean up database environment variables
        if self._prev_surreal_url is None:
            os.environ.pop("SURREAL_URL", None)
        else:
            os.environ["SURREAL_URL"] = self._prev_surreal_url
            
        if self._prev_surreal_user is None:
            os.environ.pop("SURREAL_USER", None)
        else:
            os.environ["SURREAL_USER"] = self._prev_surreal_user
            
        if self._prev_surreal_pass is None:
            os.environ.pop("SURREAL_PASS", None)
        else:
            os.environ["SURREAL_PASS"] = self._prev_surreal_pass

        # Clean up mock PATH environment
        if self._prev_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._prev_path
        shutil.rmtree(self.mock_bin_dir, ignore_errors=True)

    def test_non_interactive_default_via_env(self):
        env = os.environ.copy()
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
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.assertIn("database", config)

    def test_bootstrap_creates_fallback_kanban_and_wiki_when_no_github(self):
        # Remove git repository settings to simulate no git / no github remote
        import shutil
        shutil.rmtree(os.path.join(self.workspace_dir, ".git"), ignore_errors=True)

        env = os.environ.copy()
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


class TestScaffoldTemplatesReferenceDocsConventions(unittest.TestCase):
    """CLAUDE.md.template and AGENTS.md.template are what a freshly scaffolded
    project's instruction files are interpolated from; they must carry the
    docs/specs and docs/adrs references so a new install starts wired (#236)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "solomon_harness", "templates",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _interpolate(self, template_name):
        from solomon_harness.bootstrap import interpolate_and_write

        dest = os.path.join(self.tmp.name, template_name)
        interpolate_and_write(
            os.path.join(self.templates_dir, template_name),
            dest,
            {"PROJECT_NAME": "acme", "TECH_STACK": "Python", "GIT_REMOTE": "none"},
            "",
        )
        with open(dest, "r", encoding="utf-8") as f:
            return f.read()

    def test_claude_md_template_references_specs_and_adrs(self):
        content = self._interpolate("CLAUDE.md.template")
        self.assertIn("docs/specs/", content)
        self.assertIn("docs/adrs/", content)

    def test_agents_md_template_references_specs_and_adrs(self):
        content = self._interpolate("AGENTS.md.template")
        self.assertIn("docs/specs/", content)
        self.assertIn("docs/adrs/", content)


class TestRetrofitInstructionDocs(unittest.TestCase):
    """retrofit_instruction_docs upserts the docs/specs and docs/adrs
    references into an ALREADY-INSTALLED project's instruction files that
    predate the convention (#236 R4: no bootstrap.py precedent for this
    retrofit case). It never creates a file that doesn't already exist —
    that stays the scaffold/copy path's job, not the retrofit's."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name
        os.makedirs(os.path.join(self.workspace, "agents"), exist_ok=True)
        os.makedirs(os.path.join(self.workspace, ".github"), exist_ok=True)
        self.claude_md = os.path.join(self.workspace, "CLAUDE.md")
        self.agents_md = os.path.join(self.workspace, "agents", "AGENTS.md")
        self.agy_md = os.path.join(self.workspace, "AGY.md")
        self.copilot_md = os.path.join(self.workspace, ".github", "copilot-instructions.md")
        for path in (self.claude_md, self.agents_md, self.agy_md, self.copilot_md):
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Pre-existing instructions\n\nNo mention of the record trees here.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_inserts_missing_references_into_every_existing_file(self):
        from solomon_harness.bootstrap import retrofit_instruction_docs

        retrofit_instruction_docs(self.workspace)

        for path in (self.claude_md, self.agents_md, self.agy_md, self.copilot_md):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("docs/specs/", content, f"{path} missing docs/specs/ reference")
            self.assertIn("docs/adrs/", content, f"{path} missing docs/adrs/ reference")

    def test_rerun_adds_zero_duplicate_references(self):
        from solomon_harness.bootstrap import retrofit_instruction_docs

        retrofit_instruction_docs(self.workspace)
        with open(self.claude_md, "r", encoding="utf-8") as f:
            after_first_run = f.read()

        retrofit_instruction_docs(self.workspace)
        with open(self.claude_md, "r", encoding="utf-8") as f:
            after_second_run = f.read()

        self.assertEqual(after_first_run, after_second_run)
        self.assertEqual(after_second_run.count("docs/specs/"), 1)
        self.assertEqual(after_second_run.count("docs/adrs/"), 1)

    def test_does_not_create_a_missing_file(self):
        from solomon_harness.bootstrap import retrofit_instruction_docs

        os.remove(self.copilot_md)
        retrofit_instruction_docs(self.workspace)
        self.assertFalse(os.path.isfile(self.copilot_md))

    def test_leaves_a_file_already_carrying_both_references_untouched(self):
        from solomon_harness.bootstrap import retrofit_instruction_docs

        with open(self.claude_md, "w", encoding="utf-8") as f:
            f.write("# Already wired\n\ndocs/specs/ and docs/adrs/ are both mentioned.\n")
        before = open(self.claude_md, "r", encoding="utf-8").read()

        retrofit_instruction_docs(self.workspace)

        after = open(self.claude_md, "r", encoding="utf-8").read()
        self.assertEqual(before, after)

    def test_rerun_is_idempotent_for_a_file_with_only_one_marker_present(self):
        """A file that already mentions docs/specs/ for an unrelated reason
        (but not docs/adrs/) must not accumulate a fresh block on every run
        (PR #284 review, qa gate M1: the raw AND-substring check let a
        partial-match file's reference get duplicated across reruns)."""
        from solomon_harness.bootstrap import retrofit_instruction_docs

        with open(self.claude_md, "w", encoding="utf-8") as f:
            f.write("# Partially wired\n\nSee docs/specs/ for background context on this repo.\n")

        retrofit_instruction_docs(self.workspace)
        with open(self.claude_md, "r", encoding="utf-8") as f:
            after_first_run = f.read()
        self.assertIn("docs/adrs/", after_first_run)

        retrofit_instruction_docs(self.workspace)
        with open(self.claude_md, "r", encoding="utf-8") as f:
            after_second_run = f.read()

        self.assertEqual(after_first_run, after_second_run)

    def test_insertion_leaves_a_dedicated_marker_for_robust_redetection(self):
        """A raw substring scan is fooled by unrelated prose in either
        direction; a dedicated marker makes our own insertion unambiguous
        to detect on a later run, regardless of what else the file says
        (PR #284 review, qa gate M1)."""
        from solomon_harness.bootstrap import RETROFIT_MARKER, retrofit_instruction_docs

        retrofit_instruction_docs(self.workspace)

        with open(self.claude_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(RETROFIT_MARKER, content)


class TestFreshInstallScaffoldsCopilotInstructions(unittest.TestCase):
    """A fresh install must carry .github/copilot-instructions.md wired with
    the docs/specs and docs/adrs references, per #236's own acceptance
    scenario (PR #284 review, qa gate blocker B1: only CLAUDE.md, AGY.md, and
    agents/AGENTS.md were scaffolded; .github/copilot-instructions.md was
    never created by any code path on a truly fresh install)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_copilot_instructions_scaffolded_and_wired_on_fresh_install(self):
        from solomon_harness import bootstrap

        bootstrap._install_harness_files(self.workspace)

        path = os.path.join(self.workspace, ".github", "copilot-instructions.md")
        self.assertTrue(os.path.isfile(path), ".github/copilot-instructions.md was not scaffolded")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/specs/", content)
        self.assertIn("docs/adrs/", content)


if __name__ == "__main__":
    unittest.main()
