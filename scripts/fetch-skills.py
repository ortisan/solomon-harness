#!/usr/bin/env python3
"""Fetch agent skills from external skill-server repositories.

Sources are listed in skill-sources.json at the repository root. A source is a
git repository whose skill files (a folder with SKILL.md, or Markdown files
under a 'skills' directory) are copied into an agent's skills directory, so an
agent can reuse skills published elsewhere instead of authoring everything here.

Usage:
  python scripts/fetch-skills.py sources
  python scripts/fetch-skills.py list <source>
  python scripts/fetch-skills.py add <source> <skill> --agent <name>
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def workspace_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


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

    A skill is a folder containing SKILL.md (name is the folder name), or a
    Markdown file directly under a directory named 'skills' (name is the file
    stem). Folder SKILL.md wins on a name clash.
    """
    found: dict = {}
    for dirpath, dirnames, filenames in os.walk(tree_root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        if os.path.basename(dirpath) == "skills":
            for filename in filenames:
                if filename.endswith(".md") and filename != "SKILL.md":
                    found.setdefault(filename[:-3], os.path.join(dirpath, filename))
    for dirpath, dirnames, filenames in os.walk(tree_root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        if "SKILL.md" in filenames:
            found[os.path.basename(dirpath)] = os.path.join(dirpath, "SKILL.md")
    return found


def install_skill(src_path: str, agent_skills_dir: str, name: str) -> str:
    """Copies a skill file into an agent's skills directory as <name>.md."""
    os.makedirs(agent_skills_dir, exist_ok=True)
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


def main(argv=None) -> int:
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
    root = workspace_root()

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
