import os
import json
import shutil
import datetime
import subprocess
from typing import List, Dict

def get_project_metadata(workspace_root: str) -> tuple[str, str, str]:
    """Extracts project name, git remote, and detected technologies."""
    project_name = ""
    # 1. Package.json
    package_json = os.path.join(workspace_root, "package.json")
    if os.path.isfile(package_json):
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                project_name = json.load(f).get("name", "")
        except Exception:
            pass

    # 2. Pubspec.yaml
    if not project_name:
        pubspec = os.path.join(workspace_root, "pubspec.yaml")
        if os.path.isfile(pubspec):
            try:
                with open(pubspec, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("name:"):
                            project_name = line.split(":", 1)[1].strip()
                            break
            except Exception:
                pass

    # 3. Pyproject.toml
    if not project_name:
        pyproject = os.path.join(workspace_root, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                # Basic parsing if toml is not installed, or try to import tomllib
                import tomllib
                with open(pyproject, "rb") as fb:
                    project_name = tomllib.load(fb).get("project", {}).get("name", "")
            except Exception:
                try:
                    with open(pyproject, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("name ="):
                                project_name = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass

    if not project_name:
        project_name = os.path.basename(os.path.abspath(workspace_root))

    # Git Remote
    try:
        git_remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=workspace_root,
            stderr=subprocess.DEVNULL,
            text=True,
            # Strip GIT_* so a worktree/hook context does not redirect this to the
            # enclosing repo (see solomon_harness.home._clean_git_env / issue #24).
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        ).strip()
    except Exception:
        git_remote = "none"

    # Scan for technologies
    tech_list = []
    # Helper to check if any file with extensions or specific files exist
    def has_file_with_ext(exts: List[str], max_depth: int = 3) -> bool:
        for root, dirs, files in os.walk(workspace_root):
            depth = root[len(workspace_root):].count(os.sep)
            if depth >= max_depth:
                dirs[:] = []  # Don't descend further
                continue
            for file in files:
                if any(file.endswith(ext) for ext in exts):
                    return True
        return False

    def has_file_named(names: List[str]) -> bool:
        return any(os.path.exists(os.path.join(workspace_root, name)) for name in names)

    if has_file_named(["pubspec.yaml", "pubspec.lock", ".dart_tool"]) or has_file_with_ext([".dart"]):
        tech_list.append("Dart")
    if has_file_named(["package.json", "tsconfig.json", "node_modules"]) or has_file_with_ext([".js", ".ts"]):
        tech_list.append("JavaScript/TypeScript")
    if has_file_named(["requirements.txt", "pyproject.toml", "setup.py"]) or has_file_with_ext([".py"]):
        tech_list.append("Python")
    if has_file_named(["Cargo.toml", "Cargo.lock"]):
        tech_list.append("Rust")
    if has_file_named(["go.mod"]):
        tech_list.append("Go")
    if has_file_named(["Gemfile", "Gemfile.lock"]):
        tech_list.append("Ruby")
    if has_file_named(["build.gradle", "pom.xml"]):
        tech_list.append("Java/Kotlin")

    if not tech_list:
        tech_list.append("Generic/Shell")

    technologies = ", ".join(tech_list)
    return project_name, git_remote, technologies


def ensure_database_config(workspace_root: str) -> str:
    """Ensure .agent/config.json points at the shared SurrealDB with a per-project
    tenant database, and return the tenant id.

    The memory backend is shared across all projects on the machine (one
    SurrealDB), so each project is isolated by its own database (the tenant),
    derived from the git remote. No credentials are written here; they come from
    SURREAL_USER / SURREAL_PASS at runtime.
    """
    from solomon_harness.home import assigned_memory_port, derive_tenant

    config_dir = os.path.join(workspace_root, ".agent")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.json")

    config_data = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception:
            pass

    tenant = derive_tenant(workspace_root)
    port = assigned_memory_port()
    db = config_data.setdefault("database", {})
    db.setdefault("provider", "surrealdb")
    db.setdefault("namespace", "solomon")
    # Point at the shared backend on its assigned host port, migrating the legacy
    # default but preserving a custom URL the user set.
    if db.get("url") in (None, "", "ws://localhost:8000/rpc"):
        db["url"] = f"ws://localhost:{port}/rpc"
    # Adopt the tenant as the database, migrating the legacy shared default
    # ("harness") but preserving an explicit name the user set.
    if db.get("database") in (None, "", "harness"):
        db["database"] = tenant

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    return db["database"]


def interpolate_and_write(template_path: str, dest_path: str, replacements: Dict[str, str], fallback_content: str) -> None:
    """Interpolates template content with placeholders and writes to target destination."""
    content = fallback_content
    if os.path.isfile(template_path):
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            for key, val in replacements.items():
                content = content.replace(f"{{{{{key}}}}}", val)
        except Exception as e:
            print(f"Warning: Failed to interpolate template {template_path}: {e}")

    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def has_github_project_and_wiki(workspace_root: str, git_remote: str) -> bool:
    """Checks if the target repository has active project boards and wiki on GitHub."""
    if git_remote == "none" or "github.com" not in git_remote:
        return False
    try:
        out = subprocess.check_output(
            ["gh", "repo", "view", "--json", "hasWikiEnabled,hasProjectsEnabled"],
            cwd=workspace_root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0
        )
        data = json.loads(out)
        return data.get("hasWikiEnabled", False) and data.get("hasProjectsEnabled", False)
    except Exception:
        wiki_dir = os.path.join(workspace_root, "docs", "wiki")
        if os.path.isdir(wiki_dir) and os.listdir(wiki_dir):
            return True
        return False


def _install_harness_files(workspace_root: str) -> None:
    """Copy the harness files into a fresh project (no-op when already present).

    The source is this package's repository (resolved from __file__), so running
    `solomon-harness init` from a clone or editable install scaffolds the harness
    into the current project. When workspace_root already has agents/, nothing is
    copied and the workspace is configured in place.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.abspath(repo_root) == os.path.abspath(workspace_root):
        return  # developing the harness in place
    if os.path.isdir(os.path.join(workspace_root, "agents")):
        return  # already installed
    if not os.path.isdir(os.path.join(repo_root, "agents")):
        return  # the harness tree is not bundled with this install

    print("Installing harness files into the project...")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "build", "node_modules")
    trees = ["agents", "scripts", "solomon_harness", "docs", ".claude", ".gemini"]
    # No per-project docker-compose.yml: the memory backend is a single shared
    # instance in ~/.solomon-harness (see solomon_harness/memory.py).
    files = [
        ".mcp.json", "pyproject.toml", "uv.lock",
        "AGENTS.md", "GEMINI.md", "CLAUDE.md", "README.md", "skill-sources.json",
    ]
    for tree in trees:
        src = os.path.join(repo_root, tree)
        dest = os.path.join(workspace_root, tree)
        if os.path.isdir(src) and not os.path.exists(dest):
            shutil.copytree(src, dest, ignore=ignore)
    for name in files:
        src = os.path.join(repo_root, name)
        dest = os.path.join(workspace_root, name)
        if os.path.isfile(src) and not os.path.exists(dest):
            shutil.copy2(src, dest)
    print("  Harness files installed.")


def scaffold_agents(workspace_root: str) -> None:
    """Ensure each agent has main.py and .agent/config.json (create-only).

    Non-destructive: a hand-authored entrypoint or config is never overwritten;
    only genuinely missing scaffolding is filled in from the bundled template.
    """
    agents_dir = os.path.join(workspace_root, "agents")
    if not os.path.isdir(agents_dir):
        return
    package_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(package_dir, "templates", "harness")
    main_src = os.path.join(template_dir, "main.py")
    config_src = os.path.join(template_dir, ".agent", "config.json")

    for name in sorted(os.listdir(agents_dir)):
        agent_dir = os.path.join(agents_dir, name)
        if not os.path.isfile(os.path.join(agent_dir, "agents", f"{name}.md")):
            continue  # not an agent directory

        main_dst = os.path.join(agent_dir, "main.py")
        if os.path.isfile(main_src) and not os.path.isfile(main_dst):
            shutil.copy2(main_src, main_dst)

        config_dst = os.path.join(agent_dir, ".agent", "config.json")
        if os.path.isfile(config_src) and not os.path.isfile(config_dst):
            os.makedirs(os.path.dirname(config_dst), exist_ok=True)
            with open(config_src, "r", encoding="utf-8") as f:
                content = f.read().replace("{{AGENT_NAME}}", name)
            with open(config_dst, "w", encoding="utf-8") as f:
                f.write(content)


def bootstrap_project(workspace_root: str, non_interactive: bool = False) -> None:
    """Initializes the agent harness workspace in workspace_root.

    init is non-interactive; the ``non_interactive`` parameter is kept for CLI
    compatibility and has no effect now that pattern prompting was retired.
    """
    from solomon_harness.voice import say

    print(say("bootstrapping the agent workspace"))

    # Check prerequisites and install the safe ones (uv) before doing any work.
    try:
        from solomon_harness.prereqs import check_prerequisites

        check_prerequisites(auto_install=True)
    except Exception as exc:
        print(f"  Warning: prerequisite check failed: {exc}")

    # When run in a fresh project (no agents/ yet), install the harness files from
    # this package's repository into the workspace before configuring it.
    _install_harness_files(workspace_root)

    project_name, git_remote, technologies = get_project_metadata(workspace_root)
    print(f"  - Project Name: {project_name}")
    print(f"  - Git Remote:   {git_remote}")
    print(f"  - Technologies: {technologies}")

    # Enforce GitHub prerequisites if the project is hosted on GitHub
    if "github.com" in git_remote and not os.environ.get("SOLOMON_SKIP_GH_CHECK"):
        print("Checking GitHub prerequisites (Wiki and Project)...")
        import sys
        
        # Resolve Wiki remote URL to check initialization
        remote_url = git_remote.rstrip('/')
        if remote_url.endswith('.wiki.git'):
            wiki_url = remote_url
        elif remote_url.endswith('.wiki'):
            wiki_url = remote_url + '.git'
        elif remote_url.endswith('.git'):
            wiki_url = remote_url[:-4] + '.wiki.git'
        else:
            wiki_url = remote_url + '.wiki.git'
            
        # Resolve GitHub web wiki URL for instructions
        web_wiki_url = remote_url
        if web_wiki_url.startswith("git@"):
            try:
                parts = web_wiki_url.split("@", 1)[1].split(":", 1)
                domain = parts[0]
                path = parts[1]
                web_wiki_url = f"https://{domain}/{path}"
            except Exception:
                web_wiki_url = web_wiki_url.replace("git@", "https://").replace(":", "/")
        if web_wiki_url.endswith(".git"):
            web_wiki_url = web_wiki_url[:-4]
        web_wiki_url = web_wiki_url + "/wiki"
            
        try:
            out = subprocess.check_output(
                ["gh", "repo", "view", "--json", "hasWikiEnabled,hasProjectsEnabled"],
                cwd=workspace_root,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0
            )
            data = json.loads(out)
            
            wiki_enabled = data.get("hasWikiEnabled", False)
            projects_ok = data.get("hasProjectsEnabled", False)
            
            # Check if the Wiki repository is initialized (first page created)
            wiki_initialized = False
            if wiki_enabled:
                try:
                    subprocess.check_output(
                        ["git", "ls-remote", wiki_url],
                        stderr=subprocess.DEVNULL,
                        timeout=5.0
                    )
                    wiki_initialized = True
                except Exception:
                    pass
            
            wiki_ok = wiki_enabled and wiki_initialized
            
            wiki_icon = "\033[32m✓\033[0m" if wiki_ok else "\033[31m✗\033[0m"
            projects_icon = "\033[32m✓\033[0m" if projects_ok else "\033[31m✗\033[0m"
            
            print(f"  {wiki_icon}  GitHub Wiki")
            print(f"  {projects_icon}  GitHub Projects")
            
            if not wiki_ok or not projects_ok:
                print("\nError: Prerequisite checks failed. Please enable the missing features in your GitHub repository settings.")
                if not wiki_enabled:
                    print("  - Enable Wikis: Settings -> General -> Features -> Wikis")
                elif not wiki_initialized:
                    print(f"  - Initialize Wiki: Visit {web_wiki_url} and click 'Create the first page' or 'Save page'.")
                if not projects_ok:
                    print("  - Enable Projects: Settings -> General -> Features -> Projects")
                sys.exit(1)
                
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            print(f"Error: Failed to verify GitHub repository settings via gh CLI: {error_msg}")
            print("Please ensure you are authenticated via 'gh auth login' and have access to the repository.")
            sys.exit(1)
        except Exception as e:
            print(f"Error checking GitHub prerequisites: {e}")
            sys.exit(1)

    tenant = ensure_database_config(workspace_root)
    try:
        from solomon_harness.home import assigned_memory_port
        from solomon_harness.memory import ensure_home_compose

        port = assigned_memory_port()
        ensure_home_compose()
        print(f"  - Memory tenant: {tenant} (shared SurrealDB on host port {port})")
    except Exception as exc:
        print(f"  Warning: could not prepare the shared memory home: {exc}")

    # 3. Generate .claude/settings.json only when it does not already exist, so
    # re-running init never clobbers a hand-maintained settings file. No model is
    # pinned (the host tool decides), and permissions use the Bash(<cmd>:*) form.
    claude_settings_dir = os.path.join(workspace_root, ".claude")
    os.makedirs(claude_settings_dir, exist_ok=True)
    claude_settings_path = os.path.join(claude_settings_dir, "settings.json")
    if not os.path.isfile(claude_settings_path):
        print("Generating .claude/settings.json...")
        claude_settings = {
            "permissions": {
                "allow": [
                    "Bash(git status:*)",
                    "Bash(git diff:*)",
                    "Bash(git log:*)",
                ],
                "ask": [
                    "Bash(git commit:*)",
                    "Bash(git push:*)",
                ],
            },
            # On session start, bring the memory backend up (docker compose) and
            # then resume the project status. Both degrade gracefully, so a
            # missing Docker daemon never blocks the session.
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "uv run python -m solomon_harness.cli memory-up 2>/dev/null || true",
                            },
                            {
                                "type": "command",
                                "command": "uv run python -m solomon_harness.cli run 2>/dev/null || true",
                            },
                        ]
                    }
                ]
            },
        }
        with open(claude_settings_path, "w", encoding="utf-8") as f:
            json.dump(claude_settings, f, indent=2)
    else:
        print("Keeping existing .claude/settings.json.")

    # Resolve templates directory (bundled inside the package or root fallback)
    package_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_templates_dir = os.path.join(package_dir, "templates")
    local_templates_dir = os.path.join(workspace_root, "templates")

    # If the user has a custom templates folder in the root, prefer that
    templates_dir = local_templates_dir if os.path.isdir(local_templates_dir) else bundled_templates_dir

    # Format technologies as an unordered list for the tech stack
    tech_list = [t.strip() for t in technologies.split(",")]
    tech_stack_list = "\n".join(f"  - {t}" for t in tech_list)

    # Resolve GitHub web repo URL for links
    web_repo_url = git_remote.rstrip('/')
    if web_repo_url.startswith("git@"):
        try:
            parts = web_repo_url.split("@", 1)[1].split(":", 1)
            domain = parts[0]
            path = parts[1]
            web_repo_url = f"https://{domain}/{path}"
        except Exception:
            web_repo_url = web_repo_url.replace("git@", "https://").replace(":", "/")
    if web_repo_url.endswith(".git"):
        web_repo_url = web_repo_url[:-4]

    generation_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    replacements = {
        "PROJECT_NAME": project_name,
        "GIT_REMOTE": git_remote,
        "WEB_REPO_URL": web_repo_url,
        "TECHNOLOGIES": technologies,
        "TECH_STACK": technologies,
        "TECH_STACK_LIST": tech_stack_list,
        "GENERATION_DATE": generation_date
    }

    claude_fallback = f"""# {project_name} - Workspace Rules

## Metadata
- **Project Name:** {project_name}
- **Git Remote:** {git_remote}
- **Technologies:** {technologies}
- **Generated:** {generation_date}

## Assistant Guidelines
- Always conform to the Development Workflow.
- Ensure all commits pass the commit-msg git hook (Conventional Commits, no emojis).
- Keep code clean, test-driven (TDD), and well-documented."""

    agents_fallback = f"""# {project_name} - Agent Customizations

## Profile
- **Project Name:** {project_name}
- **Core Stack:** {technologies}
- **Repository:** {git_remote}

## Customization Rules
- Before starting any implementation, always write a PLAN.md.
- Follow TDD cycles: Red, Green, Refactor.
- Sync the documentation/wiki using scripts/wiki-sync.sh upon releases."""

    # Write CLAUDE.md and agents/AGENTS.md only when missing. These are the
    # canonical, hand-maintained rules files; init must scaffold them for a fresh
    # workspace but never overwrite them on an existing one.
    claude_md_path = os.path.join(workspace_root, "CLAUDE.md")
    if not os.path.isfile(claude_md_path):
        interpolate_and_write(
            os.path.join(templates_dir, "CLAUDE.md.template"),
            claude_md_path,
            replacements,
            claude_fallback,
        )
    else:
        print("Keeping existing CLAUDE.md.")

    agents_md_path = os.path.join(workspace_root, "agents", "AGENTS.md")
    if not os.path.isfile(agents_md_path):
        interpolate_and_write(
            os.path.join(templates_dir, "AGENTS.md.template"),
            agents_md_path,
            replacements,
            agents_fallback,
        )
    else:
        print("Keeping existing agents/AGENTS.md.")

    # 6. Install Git commit-msg hook
    print("Installing Git commit-msg hook...")
    try:
        hooks_dir_bytes = subprocess.check_output(["git", "rev-parse", "--git-path", "hooks"], cwd=workspace_root, stderr=subprocess.DEVNULL)
        hooks_dir = os.path.abspath(os.path.join(workspace_root, hooks_dir_bytes.decode("utf-8").strip()))
    except Exception:
        hooks_dir = os.path.join(workspace_root, ".git", "hooks")

    # Locate source commit-msg hook
    hook_src = os.path.join(workspace_root, "scripts", "git-hooks", "commit-msg")
    if os.path.isfile(hook_src):
        os.makedirs(hooks_dir, exist_ok=True)
        hook_dest = os.path.join(hooks_dir, "commit-msg")
        shutil.copy2(hook_src, hook_dest)
        try:
            os.chmod(hook_dest, 0o755)
            print(f"  Hook installed to {hook_dest}")
        except Exception as e:
            print(f"  Warning: Failed to set executable permissions on hook: {e}")
    else:
        print("  Warning: Git commit-msg hook template not found. Hook was not installed.")

    # 7. Scaffold any missing agent entrypoints/config.
    print("Scaffolding agent entrypoints...")
    scaffold_agents(workspace_root)

    # 8. Generate the host-tool subagent definitions from the central agents/ source.
    gi_path = os.path.join(workspace_root, "scripts", "generate-integrations.py")
    if os.path.isfile(gi_path):
        print("Generating host-tool integrations...")
        import importlib.util

        try:
            spec = importlib.util.spec_from_file_location("generate_integrations", gi_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.generate(workspace_root)
        except Exception as exc:
            print(f"  Warning: failed to generate integrations: {exc}")

    # 8b. Select the agents this project's stack needs and record them, and create
    # the GitHub delivery board when the project lives on GitHub.
    try:
        from solomon_harness.agent_selection import select_agents

        enabled = select_agents(workspace_root)
        if enabled:
            print(f"Selected agents for this stack: {', '.join(enabled)}")
            cfg_path = os.path.join(workspace_root, ".agent", "config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["enabled_agents"] = enabled
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
    except Exception as exc:
        print(f"  Warning: agent selection failed: {exc}")

    if "github.com" in git_remote:
        try:
            from solomon_harness.github import ensure_labels, ensure_project_board

            board = ensure_project_board()
            if board.get("ok"):
                action = "Created" if board.get("created") else "Found"
                print(f"  {action} GitHub delivery board 'solomon'.")
            else:
                print(f"  Note: could not set up the GitHub board: {board.get('error')}")

            labels = ensure_labels()
            if labels.get("ok"):
                print(f"  Ensured {len(labels['labels'])} standard issue labels.")
            else:
                print("  Note: could not create all standard labels (check gh auth).")
        except Exception as exc:
            print(f"  Note: GitHub setup skipped: {exc}")

    # 9. Create fallback Kanban board if not present on GitHub
    if not has_github_project_and_wiki(workspace_root, git_remote):
        print("GitHub project/wiki not detected. Initializing local Kanban board...")
        kanban_path = os.path.join(workspace_root, "planning", "KANBAN.md")
        if not os.path.exists(kanban_path):
            interpolate_and_write(
                os.path.join(templates_dir, "KANBAN.md.template"),
                kanban_path,
                replacements,
                f"# Kanban Board - {project_name}\n\nLocal Kanban board template."
            )
            print(f"  Created local Kanban board: {kanban_path}")
            
    # Always initialize local Wiki templates if the directory is empty, so they can be synced
    wiki_dir = os.path.join(workspace_root, "docs", "wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    if not os.listdir(wiki_dir):
        wiki_templates = [
            ("Home.md.template", "Home.md"),
            ("Business-Requirements.md.template", "Business-Requirements.md"),
            ("Technical-Documentation.md.template", "Technical-Documentation.md"),
            ("Features.md.template", "Features.md"),
            ("Quick-Start.md.template", "Quick-Start.md"),
            ("Release-Notes.md.template", "Release-Notes.md"),
            ("Design-System.md.template", "Design-System.md"),
            ("_Sidebar.md.template", "_Sidebar.md")
        ]
        for src_name, dest_name in wiki_templates:
            interpolate_and_write(
                os.path.join(templates_dir, "wiki", src_name),
                os.path.join(wiki_dir, dest_name),
                replacements,
                f"# {dest_name.replace('.md', '')}\n\nLocal Wiki page template."
            )
        print(f"  Created local Wiki templates inside {wiki_dir}")

    # 10. Index project codebase into database memory, then refresh the wiki overview.
    try:
        from solomon_harness.tools.database_client import DatabaseClient
        with DatabaseClient(harness_dir=workspace_root) as db:
            index_codebase(workspace_root, db)
            overview_path = write_code_overview(workspace_root, db)
            print(f"  Wrote code overview to {os.path.relpath(overview_path, workspace_root)}")
    except Exception as e:
        print(f"  Warning: Codebase indexing failed: {e}")

    print("=== Bootstrap Completed Successfully ===")
    print(
        "  Tip: run 'solomon-harness install-global' to install the agents and "
        "/solomon-* commands into ~/.claude once, so every project shares them."
    )


def index_codebase(workspace_root: str, db) -> None:
    """Index the codebase into the memory incrementally.

    Only new or changed files (by modification time and size) are read and stored;
    deleted files are removed. A manifest of path -> signature is kept in the memory
    under "__code_index_manifest__", so re-indexing does not re-scan everything every
    time -- it only touches what changed.
    """
    import json as _json

    print("Indexing project codebase into database...")
    exclude_dirs = {
        ".git", "node_modules", ".venv", "venv", "build", "dist", ".solomon",
        ".claude", ".gemini", "docs", "planning", "__pycache__", ".idea",
        ".vscode", "memory",
    }
    exclude_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar",
        ".gz", ".exe", ".bin", ".woff", ".woff2", ".eot", ".ttf", ".mp4",
        ".mp3", ".wav", ".svg", ".lock", ".pyc", ".pyo", ".db",
    }
    manifest_key = "__code_index_manifest__"

    old_manifest = {}
    raw = db.get_memory(manifest_key)
    if raw:
        try:
            old_manifest = _json.loads(raw)
        except Exception:
            old_manifest = {}

    new_manifest = {}
    indexed = 0
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if os.path.splitext(file)[1].lower() in exclude_exts:
                continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, workspace_root)
            try:
                st = os.stat(file_path)
            except OSError:
                continue
            if st.st_size > 250000:
                continue
            signature = f"{int(st.st_mtime)}:{st.st_size}"
            new_manifest[rel_path] = signature
            if old_manifest.get(rel_path) == signature:
                continue  # unchanged: skip the read and the write
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                db.save_memory(key=rel_path, value=content, category="codebase_index")
                indexed += 1
            except Exception:
                new_manifest.pop(rel_path, None)  # re-try this file next run

    removed = 0
    for rel_path in old_manifest:
        if rel_path not in new_manifest:
            db.delete_memory(rel_path)
            removed += 1

    db.save_memory(key=manifest_key, value=_json.dumps(new_manifest), category="index")
    unchanged = len(new_manifest) - indexed
    print(
        f"Indexed {indexed} new/changed file(s), skipped {unchanged} unchanged, "
        f"removed {removed} deleted."
    )


def generate_code_overview(workspace_root: str, db) -> str:
    """Build a Markdown overview of the scanned codebase from the index manifest."""
    import json as _json

    project_name, git_remote, technologies = get_project_metadata(workspace_root)

    paths = []
    raw = db.get_memory("__code_index_manifest__")
    if raw:
        try:
            paths = sorted(_json.loads(raw).keys())
        except Exception:
            paths = []

    ext_counts: Dict[str, int] = {}
    top_dirs: Dict[str, int] = {}
    for p in paths:
        ext = os.path.splitext(p)[1].lower() or "(none)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        head = p.split(os.sep)[0] if os.sep in p else "(root)"
        top_dirs[head] = top_dirs.get(head, 0) + 1

    agents = []
    agents_dir = os.path.join(workspace_root, "agents")
    if os.path.isdir(agents_dir):
        agents = sorted(
            n for n in os.listdir(agents_dir)
            if os.path.isfile(os.path.join(agents_dir, n, "agents", f"{n}.md"))
        )

    lines = [
        f"# {project_name} - Code Overview",
        "",
        "Auto-generated from the indexed codebase. It is refreshed on `solomon-harness init`",
        "and on each delivery (`/solomon-release`), so it stays a living view of the code.",
        "",
        "## Project",
        f"- Name: {project_name}",
        f"- Technologies: {technologies}",
        f"- Repository: {git_remote}",
        f"- Files indexed: {len(paths)}",
        "",
        "## Top-level structure",
    ]
    for name, n in sorted(top_dirs.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{name}` - {n} file(s)")
    lines += ["", "## File types"]
    for ext, n in sorted(ext_counts.items(), key=lambda x: (-x[1], x[0]))[:15]:
        lines.append(f"- `{ext}` - {n}")
    if agents:
        lines += ["", f"## Agents ({len(agents)})", ""]
        for agent in agents:
            lines.append(f"- {agent}")
    lines.append("")
    return "\n".join(lines)


def write_code_overview(workspace_root: str, db) -> str:
    """Write the code overview to the project wiki (docs/wiki/Code-Overview.md)."""
    overview = generate_code_overview(workspace_root, db)
    wiki_dir = os.path.join(workspace_root, "docs", "wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    path = os.path.join(wiki_dir, "Code-Overview.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(overview)
    return path
