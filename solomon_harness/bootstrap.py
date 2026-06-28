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
                with open(pyproject, "rb") as f:
                    project_name = tomllib.load(f).get("project", {}).get("name", "")
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
            text=True
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


def configure_patterns(workspace_root: str, non_interactive: bool = False) -> tuple[str, str, str]:
    """Prompts or uses defaults for software architecture/observability/security patterns."""
    arch_pattern = "hexagonal"
    obs_pattern = "opentelemetry"
    sec_pattern = "secure_dev"

    if not non_interactive:
        print("Software patterns configuration:")
        while True:
            print("Select Software Architecture Pattern: [1] Clean Architecture, [2] Functional Architecture, [3] Hexagonal (Ports & Adapters)")
            choice = input("Choice: ").strip()
            if choice == "1":
                arch_pattern = "clean"
                break
            elif choice == "2":
                arch_pattern = "functional"
                break
            elif choice == "3":
                arch_pattern = "hexagonal"
                break
            else:
                print("Invalid option. Please try again.")

        while True:
            print("Select Observability level: [1] Basic Logs, [2] OpenTelemetry (traces, spans, custom metrics)")
            choice = input("Choice: ").strip()
            if choice == "1":
                obs_pattern = "basic"
                break
            elif choice == "2":
                obs_pattern = "opentelemetry"
                break
            else:
                print("Invalid option. Please try again.")

        while True:
            print("Select Security practices: [1] Standard, [2] Secure Development (SAST, STRIDE threat modeling)")
            choice = input("Choice: ").strip()
            if choice == "1":
                sec_pattern = "standard"
                break
            elif choice == "2":
                sec_pattern = "secure_dev"
                break
            else:
                print("Invalid option. Please try again.")

    # Save to config.json
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

    config_data["architecture_pattern"] = arch_pattern
    config_data["observability_pattern"] = obs_pattern
    config_data["security_pattern"] = sec_pattern

    if "database" not in config_data:
        # No credentials are written here; they are supplied at runtime via the
        # SURREAL_USER / SURREAL_PASS environment variables.
        config_data["database"] = {
            "provider": "surrealdb",
            "url": "ws://localhost:8000/rpc",
            "namespace": "solomon",
            "database": "harness"
        }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    return arch_pattern, obs_pattern, sec_pattern


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


def bootstrap_project(workspace_root: str, non_interactive: bool = False) -> None:
    """Initializes the agent harness workspace in workspace_root."""
    if os.environ.get("NON_INTERACTIVE") == "true":
        non_interactive = True
    print("=== Solomon Agent Bootstrap ===")
    project_name, git_remote, technologies = get_project_metadata(workspace_root)
    print(f"  - Project Name: {project_name}")
    print(f"  - Git Remote:   {git_remote}")
    print(f"  - Technologies: {technologies}")

    arch, obs, sec = configure_patterns(workspace_root, non_interactive)

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
            }
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

    generation_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    replacements = {
        "PROJECT_NAME": project_name,
        "GIT_REMOTE": git_remote,
        "TECHNOLOGIES": technologies,
        "TECH_STACK": technologies,
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

    # 7. Compile agent harnesses
    print("Compiling agent harnesses...")
    from solomon_harness.compiler import compile_harnesses
    compile_harnesses(workspace_root)

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

    # 9. Create fallback Kanban board and Wiki template if not present on GitHub
    if not has_github_project_and_wiki(workspace_root, git_remote):
        print("GitHub project/wiki not detected. Initializing local Kanban and Wiki templates...")
        
        kanban_path = os.path.join(workspace_root, "planning", "KANBAN.md")
        wiki_dir = os.path.join(workspace_root, "docs", "wiki")
        
        if not os.path.exists(kanban_path):
            interpolate_and_write(
                os.path.join(templates_dir, "KANBAN.md.template"),
                kanban_path,
                replacements,
                f"# Kanban Board - {project_name}\n\nLocal Kanban board template."
            )
            print(f"  Created local Kanban board: {kanban_path}")
            
        os.makedirs(wiki_dir, exist_ok=True)
        if not os.listdir(wiki_dir):
            wiki_templates = [
                ("Home.md.template", "Home.md"),
                ("Business-Requirements.md.template", "Business-Requirements.md"),
                ("Technical-Documentation.md.template", "Technical-Documentation.md")
            ]
            for src_name, dest_name in wiki_templates:
                interpolate_and_write(
                    os.path.join(templates_dir, "wiki", src_name),
                    os.path.join(wiki_dir, dest_name),
                    replacements,
                    f"# {dest_name.replace('.md', '')}\n\nLocal Wiki page template."
                )
            print(f"  Created local Wiki templates inside {wiki_dir}")

    # 10. Index project codebase into database memory
    try:
        from solomon_harness.tools.database_client import DatabaseClient
        with DatabaseClient(harness_dir=workspace_root) as db:
            index_codebase(workspace_root, db)
    except Exception as e:
        print(f"  Warning: Codebase indexing failed: {e}")

    print("=== Bootstrap Completed Successfully ===")


def index_codebase(workspace_root: str, db) -> None:
    """Walks the workspace root and indexes text files into the database memory."""
    print("Indexing project codebase into database...")
    count = 0
    # Exclude common binaries, lockfiles, and hidden/build folders to save space
    exclude_dirs = {
        ".git", "node_modules", ".venv", "venv", "build", "dist",
        ".claude", ".agents", "__pycache__", "docs", "planning",
        ".idea", ".vscode"
    }
    exclude_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar",
        ".gz", ".exe", ".bin", ".woff", ".woff2", ".eot", ".ttf", ".mp4",
        ".mp3", ".wav", ".svg", ".lock", "pyc", "pyo"
    }

    for root, dirs, files in os.walk(workspace_root):
        # In-place modify dirs to avoid descending into excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in exclude_exts:
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, workspace_root)

            # Skip large files > 250KB to preserve token limits
            try:
                size = os.path.getsize(file_path)
                if size > 250000:
                    continue
            except OSError:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Use relative path as key, content as value, category "codebase_indexing"
                db.save_memory(key=rel_path, value=content, category="codebase_indexing")
                count += 1
            except Exception:
                pass

    print(f"Successfully indexed {count} files in the database.")

