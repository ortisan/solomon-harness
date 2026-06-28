import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional

def get_workspace_root(start_dir: Optional[str] = None) -> str:
    """Locate workspace root from start_dir or current working directory."""
    current = start_dir or os.getcwd()
    while current and current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, "solomon_harness")) or os.path.isdir(os.path.join(current, "agents")):
            return current
        current = os.path.dirname(current)
    return start_dir or os.getcwd()


def load_sources(root: str) -> dict:
    """Returns {name: source_dict} from skill-sources.json."""
    path = os.path.join(root, "skill-sources.json")
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


def install_skill(src_path: str, agent_skills_dir: str, name: str) -> str:
    """Installs a skill into an agent's skills directory.

    A standalone ``<name>.md`` is copied to ``<agent_skills_dir>/<name>.md``.
    A packaged ``SKILL.md`` is treated as a folder skill: its whole parent
    directory is copied to ``<agent_skills_dir>/<name>/`` so sibling assets and
    scripts are preserved. Returns the path that was written.
    """
    os.makedirs(agent_skills_dir, exist_ok=True)
    if os.path.basename(src_path) == "SKILL.md":
        target_dir = os.path.join(agent_skills_dir, name)
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(os.path.dirname(src_path), target_dir)
        return target_dir
    target = os.path.join(agent_skills_dir, f"{name}.md")
    shutil.copy2(src_path, target)
    return target


def _clone(source: dict, dest: str) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", source["url"], dest],
        check=True,
        capture_output=True,
        text=True,
    )


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
    agent_dir = os.path.join(root, "agents", agent)
    if not os.path.isdir(agent_dir):
        print(f"Error: unknown agent '{agent}' (no agents/{agent}).", file=sys.stderr)
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
        target = install_skill(skills[skill], os.path.join(agent_dir, "skills"), skill)
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
