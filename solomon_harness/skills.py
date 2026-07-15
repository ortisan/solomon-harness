import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, List, Optional

from solomon_harness.layout import (
    HarnessPaths,
    PathConfinementError,
    confined_path,
    confined_read_path,
    find_workspace_root,
)


def get_workspace_root(start_dir: Optional[str] = None) -> str:
    """Locate workspace root from start_dir or current working directory."""
    return os.fspath(find_workspace_root(start_dir))


def load_sources(root: str) -> dict:
    """Returns {name: source_dict} from skill-sources.json."""
    path = os.fspath(HarnessPaths(root).resolve_skill_sources())
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["name"]: s for s in data.get("sources", []) if "name" in s}


def discover_skill_files(tree_root: str) -> dict:
    """Returns {skill_name: absolute_path} for skill files under tree_root.

    The walk sorts directory and file names so that, when two distinct paths
    map to the same skill stem, precedence is deterministic instead of
    depending on the OS-specific os.walk order. A warning naming both paths is
    emitted to stderr on every collision. Standalone files under a ``skills/``
    directory are discovered first; a packaged ``SKILL.md`` then overrides a
    standalone file of the same stem, matching the original precedence.
    """
    found: dict = {}

    def register(stem: str, path: str, override: bool) -> None:
        existing = found.get(stem)
        if existing is not None and existing != path:
            print(
                f"Warning: duplicate skill stem '{stem}' found at "
                f"{existing} and {path}",
                file=sys.stderr,
            )
            if not override:
                return
        found[stem] = path

    for dirpath, dirnames, filenames in os.walk(tree_root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        if os.path.basename(dirpath) == "skills":
            for filename in sorted(filenames):
                if filename.endswith(".md") and filename != "SKILL.md":
                    register(filename[:-3], os.path.join(dirpath, filename), override=False)
    for dirpath, dirnames, filenames in os.walk(tree_root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        if "SKILL.md" in filenames:
            register(os.path.basename(dirpath), os.path.join(dirpath, "SKILL.md"), override=True)
    return found


def _validate_skill_name(name: str) -> None:
    """Reject names that can address anything but one skills child."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or ".." in name:
        raise ValueError("invalid skill name")


def _reject_tree_symlinks(path: str) -> None:
    """Reject links before copying external instruction content."""
    if os.path.islink(path):
        raise ValueError("Symlinks are rejected in imported skills")
    if not os.path.isdir(path):
        return
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.is_symlink():
                raise ValueError("Symlinks are rejected in imported skills")
            if entry.is_dir(follow_symlinks=False):
                _reject_tree_symlinks(entry.path)


def install_skill(
    src_path: str,
    agent_skills_dir: str,
    name: str,
    workspace_root: Optional[str] = None,
) -> str:
    """Installs a skill into an agent's skills directory.

    A standalone ``<name>.md`` is copied to ``<agent_skills_dir>/<name>.md``.
    A packaged ``SKILL.md`` is treated as a folder skill: its whole parent
    directory is copied to ``<agent_skills_dir>/<name>/`` so sibling assets and
    scripts are preserved. Returns the path that was written.
    """
    _validate_skill_name(name)
    _reject_tree_symlinks(src_path)
    skills_path = (
        confined_path(workspace_root, agent_skills_dir)
        if workspace_root is not None
        else os.path.abspath(agent_skills_dir)
    )
    agent_skills_dir = os.fspath(skills_path)
    os.makedirs(agent_skills_dir, exist_ok=True)
    if os.path.basename(src_path) == "SKILL.md":
        source_dir = os.path.dirname(src_path)
        _reject_tree_symlinks(source_dir)
        target_dir = os.path.join(agent_skills_dir, name)
        if workspace_root is not None:
            target_dir = os.fspath(confined_path(workspace_root, target_dir))
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        return target_dir
    target = os.path.join(agent_skills_dir, f"{name}.md")
    if workspace_root is not None:
        target = os.fspath(confined_path(workspace_root, target))
    shutil.copy2(src_path, target)
    return target


def _clone(source: dict, dest: str) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", source["url"], dest],
        check=True,
        capture_output=True,
        text=True,
    )


def _reconcile_host_adapters(root: str) -> Any:
    """Keep the install manifest and all three native adapters synchronized."""
    paths = HarnessPaths(root)
    if paths.manifest.is_file():
        from solomon_harness.install_layout import compile_project_adapters

        return compile_project_adapters(root)

    from solomon_harness.host_adapters import compile_adapters

    return compile_adapters(root)


def cmd_sources(root: str) -> int:
    sources = load_sources(root)
    if not sources:
        print("No sources configured. Add them to skill-sources.json.")
        return 0
    for name, source in sources.items():
        print(f"{name}\t{source.get('url', '')}\t{source.get('note', '')}")
    return 0


def cmd_list(root: str, source_name: str) -> int:
    sources = load_sources(root)
    source = sources.get(source_name)
    if not source:
        print(f"Error: unknown source '{source_name}'. Run 'sources' to list them.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _clone(source, tmp)
        except subprocess.CalledProcessError as exc:
            print(f"Error: failed to clone {source.get('url')}: {exc.stderr}", file=sys.stderr)
            return 1
        skills = discover_skill_files(tmp)
        if not skills:
            print("No skills found in this source.")
            return 0
        for name in sorted(skills):
            print(name)
    return 0


def cmd_add(root: str, source_name: str, skill: str, agent: str) -> int:
    sources = load_sources(root)
    source = sources.get(source_name)
    if not source:
        print(f"Error: unknown source '{source_name}'. Run 'sources' to list them.", file=sys.stderr)
        return 1
    paths = HarnessPaths(root)
    try:
        _validate_skill_name(skill)
        if not re.fullmatch(r"[a-z0-9_]+", agent):
            raise ValueError("invalid agent name")
        agents_dir = confined_path(paths.root, paths.resolve_agents())
        agent_dir = confined_path(paths.root, agents_dir / agent)
        skills_dir = confined_path(paths.root, agent_dir / "skills")
        doc_script = confined_read_path(
            paths.root, paths.resolve_scripts() / "document-skills.py"
        )
    except (PathConfinementError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not os.path.isdir(agent_dir):
        print(
            f"Error: unknown agent '{agent}' "
            f"(no {os.path.relpath(os.fspath(agent_dir), root)}).",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _clone(source, tmp)
        except subprocess.CalledProcessError as exc:
            print(f"Error: failed to clone {source.get('url')}: {exc.stderr}", file=sys.stderr)
            return 1
        skills = discover_skill_files(tmp)
        if skill not in skills:
            print(f"Error: skill '{skill}' not found in {source_name}. Run 'list {source_name}'.", file=sys.stderr)
            return 1
        try:
            target = install_skill(
                skills[skill],
                os.fspath(skills_dir),
                skill,
                workspace_root=root,
            )
        except (PathConfinementError, ValueError, OSError) as exc:
            print(f"Error: failed to install skill: {exc}", file=sys.stderr)
            return 1

    try:
        doc_script = confined_read_path(paths.root, doc_script)
        if doc_script.is_file():
            subprocess.run(  # noqa: S603 - current interpreter runs a confined repository script
                [sys.executable, os.fspath(doc_script)],
                cwd=os.fspath(paths.resolve_agents().parent),
                check=True,
            )

        compile_result = _reconcile_host_adapters(root)
    except (
        OSError,
        PathConfinementError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Error: failed to reconcile host adapters: {exc}", file=sys.stderr)
        return 1
    if compile_result.conflicts:
        print(
            "Warning: preserved conflicting host adapter files: "
            + ", ".join(compile_result.conflicts),
            file=sys.stderr,
        )
    print(f"Installed '{skill}' from {source_name} into {os.path.relpath(target, root)}")
    return 0


def main(argv: Optional[List[str]] = None, start_dir: Optional[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch agent skills from external skill-server repositories.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("sources", help="List configured skill sources")
    list_p = sub.add_parser("list", help="List skills available in a source")
    list_p.add_argument("source")
    add_p = sub.add_parser("add", help="Install a skill from a source into an agent")
    add_p.add_argument("source")
    add_p.add_argument("skill")
    add_p.add_argument("--agent", required=True)

    args = parser.parse_args(argv)
    root = get_workspace_root(start_dir)

    if args.command == "sources":
        return cmd_sources(root)
    if args.command == "list":
        return cmd_list(root, args.source)
    if args.command == "add":
        return cmd_add(root, args.source, args.skill, args.agent)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
