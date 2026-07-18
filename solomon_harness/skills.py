import argparse
import json
import os
import re
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


from solomon_harness import skill_acquisition

# The mechanical copy lives in the acquisition chokepoint; re-exported so existing
# callers/tests that reference ``skills.install_skill`` keep resolving (#108).
install_skill = skill_acquisition.install_skill

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
            skill_acquisition._pinned_clone(source, tmp)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
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
    # The one guarded chokepoint: pinned clone + scan/quarantine/confine + install.
    # There is no unpinned or unscanned path into agents/<name>/skills/ (#108).
    try:
        target = skill_acquisition.acquire_skill(
            root, source, skill, os.fspath(skills_dir)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Error: failed to fetch {source.get('url')}: {exc.stderr}", file=sys.stderr)
        return 1

    # After a successful install, keep the install manifest and every native host
    # adapter synchronized so the new skill propagates to all hosts.
    try:
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
