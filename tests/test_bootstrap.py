import json
import os
import shutil
import subprocess
import tempfile
import unittest

import pytest

from solomon_harness.subprocess_env import clean_git_env


def test_scaffold_agents_rejects_a_symlinked_canonical_catalog(tmp_path):
    from solomon_harness.bootstrap import scaffold_agents

    outside = tmp_path.parent / f"{tmp_path.name}-agents-outside"
    role = outside / "qa" / "agents" / "qa.md"
    role.parent.mkdir(parents=True)
    role.write_text("# QA\n", encoding="utf-8")
    core = tmp_path / ".agents" / "solomon"
    core.mkdir(parents=True)
    (core / "agents").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        scaffold_agents(str(tmp_path))

    assert not (outside / "qa" / "main.py").exists()


def test_scaffold_agents_rejects_a_payload_template_through_a_symlink(
    tmp_path, monkeypatch
):
    from solomon_harness import bootstrap

    workspace = tmp_path / "workspace"
    role = workspace / "agents" / "qa" / "agents" / "qa.md"
    role.parent.mkdir(parents=True)
    role.write_text("# QA\n", encoding="utf-8")

    package = tmp_path / "payload" / "solomon_harness"
    templates = package / "templates"
    templates.mkdir(parents=True)
    outside = tmp_path / "outside-templates"
    (outside / ".agent").mkdir(parents=True)
    (outside / "main.py").write_text("print('outside')\n", encoding="utf-8")
    (outside / ".agent" / "config.json").write_text(
        '{"agent_name":"{{AGENT_NAME}}"}\n', encoding="utf-8"
    )
    (templates / "harness").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(bootstrap, "__file__", str(package / "bootstrap.py"))

    with pytest.raises(ValueError, match="read path.*symlink"):
        bootstrap.scaffold_agents(str(workspace))

    assert not (workspace / "agents" / "qa" / "main.py").exists()
    assert not (workspace / "agents" / "qa" / ".agent" / "config.json").exists()


def test_scaffold_new_agent_does_not_execute_document_skills_through_a_symlink(
    tmp_path, monkeypatch
):
    from solomon_harness import bootstrap

    workspace = tmp_path / "workspace"
    agents = workspace / "agents"
    agents.mkdir(parents=True)
    (agents / "AGENTS.md").write_text(
        "# Rules\n\n## The specialist agents\n\n", encoding="utf-8"
    )
    outside_scripts = tmp_path / "outside-scripts"
    outside_scripts.mkdir()
    (outside_scripts / "document-skills.py").write_text(
        "raise RuntimeError('must not execute')\n", encoding="utf-8"
    )
    (workspace / "scripts").symlink_to(
        outside_scripts, target_is_directory=True
    )
    launched = []
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: launched.append((args, kwargs)),
    )

    class _CompileResult:
        conflicts = ()

    monkeypatch.setattr(
        bootstrap, "_reconcile_host_adapters", lambda _root: _CompileResult()
    )

    with pytest.raises(ValueError, match="read path.*symlink"):
        bootstrap.scaffold_new_agent(
            str(workspace), "escaped_agent", "Must stay confined"
        )

    assert launched == []
    assert not (agents / "escaped_agent").exists()


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

    def test_bootstrap_uses_native_three_host_adapters_and_never_gemini(self):
        from solomon_harness.bootstrap import bootstrap_project

        # This scenario is a fresh consumer install. The shared shell-bootstrap
        # fixture copies the current source tree for its subprocess cases; those
        # files are not a proven legacy payload and must not be mistaken for one.
        for legacy_source_tree in ("agents", "scripts", "solomon_harness"):
            shutil.rmtree(
                os.path.join(self.workspace_dir, legacy_source_tree),
                ignore_errors=True,
            )

        bootstrap_project(self.workspace_dir, non_interactive=True)

        self.assertFalse(os.path.exists(os.path.join(self.workspace_dir, ".gemini")))
        for relative in (
            ".claude/settings.json",
            ".agents/hooks.json",
            ".agents/plugins/solomon/mcp_config.json",
            ".codex/config.toml",
        ):
            self.assertTrue(os.path.isfile(os.path.join(self.workspace_dir, relative)), relative)

        claude_settings_path = os.path.join(self.workspace_dir, ".claude", "settings.json")
        with open(claude_settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        settings.setdefault("permissions", {}).setdefault("allow", []).append("Bash(dummy:*)")
        with open(claude_settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        bootstrap_project(self.workspace_dir, non_interactive=True)

        with open(claude_settings_path, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertIn("Bash(dummy:*)", merged["permissions"]["allow"])
        self.assertIn("SessionStart", merged["hooks"])
        self.assertIn("PreToolUse", merged["hooks"])


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

        self.assertFalse(os.path.isfile(os.path.join(self.workspace_dir, "pyproject.toml")))
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.workspace_dir, ".agents", "solomon", "pyproject.toml")
            )
        )
        self.assertFalse(os.path.exists(os.path.join(self.workspace_dir, "planning")))


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


class TestFreshInstallScaffoldsGithubTemplates(unittest.TestCase):
    """A consumer gets project record templates, not another host adapter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_pr_template_is_scaffolded_without_copilot_instructions(self):
        from solomon_harness import bootstrap

        bootstrap._install_harness_files(self.workspace)

        self.assertTrue(
            os.path.isfile(os.path.join(self.workspace, ".github", "PULL_REQUEST_TEMPLATE.md"))
        )
        self.assertFalse(
            os.path.exists(os.path.join(self.workspace, ".github", "copilot-instructions.md"))
        )


def test_bootstrap_fails_closed_when_managed_adapter_conflicts_are_preserved(
    tmp_path, monkeypatch, capsys
):
    from solomon_harness import bootstrap, install_layout, prereqs

    class _ConflictResult:
        conflicts = (".mcp.json", ".codex/config.toml")
        blocking_conflicts = conflicts

    monkeypatch.setattr(prereqs, "check_prerequisites", lambda **_kwargs: True)
    monkeypatch.setattr(install_layout, "install_project", lambda _root: _ConflictResult())

    with pytest.raises(install_layout.InstallConflictError, match=r"\.mcp\.json"):
        bootstrap.bootstrap_project(str(tmp_path), non_interactive=True)

    output = capsys.readouterr().out
    assert "Preserved 2" in output
    assert "Bootstrap Completed Successfully" not in output


def test_bootstrap_reports_nonblocking_legacy_conflicts_and_completes(
    tmp_path, monkeypatch, capsys
):
    from solomon_harness import bootstrap, install_layout, prereqs

    class _WarningResult:
        conflicts = ("agents/project-owned.md",)
        blocking_conflicts = ()

    monkeypatch.setattr(prereqs, "check_prerequisites", lambda **_kwargs: True)
    monkeypatch.setattr(install_layout, "install_project", lambda _root: _WarningResult())
    # Isolate the per-machine harness home so bootstrap's memory setup writes the
    # generated SurrealDB credentials into a throwaway dir, never the real
    # ~/.solomon-harness — a leaked credentials.json there makes the live
    # SurrealDB integration tests sign in with a non-root password (#350).
    monkeypatch.setenv("SOLOMON_HARNESS_HOME", str(tmp_path / "harness-home"))

    bootstrap.bootstrap_project(str(tmp_path), non_interactive=True)

    output = capsys.readouterr().out
    assert "Preserved 1" in output
    assert "Harness files installed" in output
    assert "Bootstrap Completed Successfully" in output


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
        # Nothing else from the harness's docs travels (ADR-0029): no wiki,
        # no conventions, no templates tree, no root README — the record
        # scaffolding above is the entire docs payload.
        self.assertFalse(os.path.isdir(os.path.join(self.workspace, "docs", "wiki")))
        self.assertFalse(os.path.isfile(os.path.join(self.workspace, "README.md")))
        self.assertFalse(
            os.path.isfile(os.path.join(self.workspace, "docs", "solomon-workflow.md"))
        )
        self.assertFalse(
            os.path.isdir(os.path.join(self.workspace, "docs", "templates"))
        )
        self.assertEqual(
            sorted(os.listdir(os.path.join(self.workspace, "docs"))),
            ["adrs", "specs"],
            "the record scaffolding is the entire docs payload of an install",
        )
