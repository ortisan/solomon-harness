#!/usr/bin/env python3
import os
import re
import sys
import unicodedata
from pathlib import Path


SOLOMON_WORKFLOW_NAMES = (
    "bug",
    "idea",
    "issue",
    "loop",
    "refine",
    "release",
    "review",
    "scan-arch",
    "scan-dedup",
    "start",
    "workflow",
)
_CANONICAL_METADATA = ("description", "argument-hint")
_CLAUDE_METADATA = (*_CANONICAL_METADATA, "allowed-tools")
_HOST_SPECIFIC_WORKFLOW_PROTOCOLS = (
    ".claude/agents",
    ".claude/commands",
    "$ARGUMENTS",
    "Antigravity CLI",
    "AskUserQuestion",
    "Claude Code",
    "Gemini CLI",
    "Task tool",
    "mcp__solomon-memory__",
)
_MAX_CLAUDE_BRIDGE_BYTES = 2048


def _split_frontmatter(content, filepath):
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        print(f"Error [{filepath}]: Missing frontmatter.")
        return None
    try:
        closing = lines.index("---", 1)
    except ValueError:
        print(f"Error [{filepath}]: Unterminated frontmatter.")
        return None

    metadata = {}
    for line in lines[1:closing]:
        if ":" not in line:
            print(f"Error [{filepath}]: Invalid frontmatter entry: {line!r}")
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value or key in metadata:
            print(f"Error [{filepath}]: Invalid frontmatter key: {key!r}")
            return None
        metadata[key] = value
    return metadata, "\n".join(lines[closing + 1 :]).strip()


def _workflow_files(directory):
    if not directory.is_dir():
        return set()
    return {path.name for path in directory.glob("solomon-*.md") if path.is_file()}


def validate_solomon_workflow_catalog(project_root):
    """Validate the neutral workflow sources and their thin Claude bridges."""

    root = Path(project_root)
    catalog = root / "solomon_harness" / "catalog" / "workflows"
    bridges = root / ".claude" / "commands"
    expected = {f"solomon-{name}.md" for name in SOLOMON_WORKFLOW_NAMES}
    success = True

    for label, directory in (("catalog", catalog), ("Claude bridge", bridges)):
        actual = _workflow_files(directory)
        if actual != expected:
            missing = ", ".join(sorted(expected - actual)) or "none"
            extra = ", ".join(sorted(actual - expected)) or "none"
            print(
                f"Error [{directory}]: {label} workflow set differs; "
                f"missing: {missing}; extra: {extra}."
            )
            success = False

    for filename in sorted(expected):
        source_path = catalog / filename
        bridge_path = bridges / filename
        if not source_path.is_file() or not bridge_path.is_file():
            continue

        source_content = source_path.read_text(encoding="utf-8")
        bridge_content = bridge_path.read_text(encoding="utf-8")
        source_parts = _split_frontmatter(source_content, source_path)
        bridge_parts = _split_frontmatter(bridge_content, bridge_path)
        if source_parts is None or bridge_parts is None:
            success = False
            continue
        source_metadata, source_body = source_parts
        bridge_metadata, bridge_body = bridge_parts

        for key in _CANONICAL_METADATA:
            if not source_metadata.get(key):
                print(f"Error [{source_path}]: Missing canonical metadata '{key}'.")
                success = False
        if "allowed-tools" in source_metadata:
            print(
                f"Error [{source_path}]: Claude-only 'allowed-tools' belongs in the bridge."
            )
            success = False
        for key in _CLAUDE_METADATA:
            if not bridge_metadata.get(key):
                print(f"Error [{bridge_path}]: Missing Claude metadata '{key}'.")
                success = False
        for key in _CANONICAL_METADATA:
            if source_metadata.get(key) != bridge_metadata.get(key):
                print(f"Error [{bridge_path}]: Metadata '{key}' differs from the catalog.")
                success = False

        allowed_tools = bridge_metadata.get("allowed-tools", "")
        memory_operations = set(
            re.findall(r"project-memory ([a-z][a-z0-9_]*)", source_body)
        )
        required_claude_tools = {
            f"mcp__solomon-memory__{operation}" for operation in memory_operations
        }
        if "host's native enumerable input mechanism" in source_body:
            required_claude_tools.add("AskUserQuestion")
        if "host's native specialist-delegation mechanism" in source_body:
            required_claude_tools.add("Task")
        for tool in sorted(required_claude_tools):
            if tool not in allowed_tools:
                print(
                    f"Error [{bridge_path}]: Claude metadata does not allow "
                    f"required host tool '{tool}'."
                )
                success = False

        if not source_body:
            print(f"Error [{source_path}]: Canonical workflow body is empty.")
            success = False
        if "{{arguments}}" not in source_body:
            print(f"Error [{source_path}]: Missing neutral '{{{{arguments}}}}' placeholder.")
            success = False
        for protocol in _HOST_SPECIFIC_WORKFLOW_PROTOCOLS:
            if protocol in source_body:
                print(
                    f"Error [{source_path}]: Host-specific protocol {protocol!r} "
                    "appears in the canonical workflow."
                )
                success = False

        expected_reference = f"`solomon_harness/catalog/workflows/{filename}`"
        bridge_lines = [line for line in bridge_body.splitlines() if line.strip()]
        if len(bridge_lines) != 2:
            print(f"Error [{bridge_path}]: Claude bridge must contain exactly two lines.")
            success = False
        if expected_reference not in bridge_body or "$ARGUMENTS" not in bridge_body:
            print(f"Error [{bridge_path}]: Claude bridge does not point to its catalog source.")
            success = False
        if len(bridge_content.encode("utf-8")) > _MAX_CLAUDE_BRIDGE_BYTES:
            print(f"Error [{bridge_path}]: Claude bridge exceeds the thin-bridge limit.")
            success = False

    return success


def has_emoji(text):
    for char in text:
        cp = ord(char)
        # Check standard emoji / symbol blocks
        is_emoji = (
            (0x1F000 <= cp <= 0x1FFFF)
            or (0x2600 <= cp <= 0x27BF)
            or (0x2300 <= cp <= 0x23FF)
        )
        if not is_emoji:
            try:
                cat = unicodedata.category(char)
                if cat == "So":  # Symbol, other
                    is_emoji = True
                else:
                    name = unicodedata.name(char, "").upper()
                    if any(word in name for word in ("EMOJI", "SMILEY", "PICTOGRAPH")):
                        is_emoji = True
            except Exception:
                pass
        if is_emoji:
            return True, char
    return False, None


def validate_yaml_formatting(content, filepath):
    lines = content.split("\n")
    for idx, line in enumerate(lines, 1):
        # YAML files must not use tabs for indentation
        if "\t" in line:
            print(
                f"Error [{filepath}:{idx}]: Contains tab characters. YAML requires spaces for indentation."
            )
            return False

        # Check for trailing spaces or basic syntax errors
        # E.g., colon must be followed by space or newline
        if ":" in line:
            # simple check: if colon is not inside quotes, it should have space after it
            # We can do a basic check for key:value without space
            parts = line.split(":")
            if len(parts) > 1:
                key = parts[0]
                val = ":".join(parts[1:])
                # Check if it looks like a key:value pair (not a URL)
                if not (
                    key.strip().startswith("http")
                    or key.strip().startswith("git@")
                    or val.startswith("//")
                ):
                    if (
                        val
                        and not val.startswith(" ")
                        and not val.startswith("\n")
                        and not val.strip() == ""
                    ):
                        print(
                            f"Error [{filepath}:{idx}]: Missing space after colon in key-value pair."
                        )
                        return False

    # Structural validity via a real YAML parse. The previous hand-rolled
    # character scanner for matched brackets/quotes produced false positives on
    # legitimate shell regexes embedded in run: blocks (a `[` inside a quoted
    # `sed` expression toggled its own quote state), so it is replaced with the
    # parser the rest of the world uses. GitHub Actions' `on:` mapping parses
    # cleanly; the parser only flags genuinely malformed YAML.
    try:
        import yaml
    except ImportError:
        # PyYAML absent: the emoji, tab, permissions and SHA-pin checks still
        # run; skip the structural parse rather than fail on a missing library.
        return True
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        detail = str(exc).replace("\n", " ")
        print(f"Error [{filepath}]: Invalid YAML: {detail}")
        return False

    return True


def validate_workflow_file(filepath, name_pattern, required_substrings):
    if not os.path.exists(filepath):
        print(f"Error: Workflow file does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print(f"Error: Workflow file is empty: {filepath}")
        return False

    # Emoji Check
    emoji_found, char = has_emoji(content)
    if emoji_found:
        print(
            f"Error: Emoji or icon '{char}' found in {filepath}. Emojis are strictly prohibited."
        )
        return False

    # Formatting Check
    if not validate_yaml_formatting(content, filepath):
        return False

    # Security Check: Explicit permissions and Pinned actions (SHAs)
    has_permissions_block = False
    lines = content.split("\n")
    for idx, line in enumerate(lines, 1):
        if "permissions:" in line:
            has_permissions_block = True

        # Match uses: actions/checkout@v4 or uses: actions/checkout@sha
        uses_match = re.search(r"uses:\s*([^\s#]+)", line)
        if uses_match:
            action_ref = uses_match.group(1)
            # Skip local actions (starting with ./)
            if not action_ref.startswith("./"):
                if "@" not in action_ref:
                    print(
                        f"Error [{filepath}:{idx}]: Action '{action_ref}' is not pinned to a version/SHA."
                    )
                    return False
                parts = action_ref.split("@")
                sha = parts[1]
                # SHA must be a 40-character hex string
                if not re.match(r"^[a-fA-F0-9]{40}$", sha):
                    print(
                        f"Error [{filepath}:{idx}]: Action '{action_ref}' must be pinned to a 40-character commit SHA for security."
                    )
                    return False

    if not has_permissions_block:
        print(f"Error [{filepath}]: Missing explicit 'permissions:' configuration.")
        return False

    # Content verification
    for substring in required_substrings:
        if substring not in content:
            print(f"Error: Required pattern '{substring}' not found in {filepath}")
            return False

    return True


def main():
    success = True

    ci_path = ".github/workflows/ci.yml"
    # Content verification asserts the CURRENT pipeline contract. The harness CI
    # is a uv-driven Python+Node gate (ruff, mypy, pytest, the Next.js cockpit);
    # the obsolete self-hosted/agent-eval substrings (bash -n, shellcheck,
    # main.py eval, compile-harnesses.py) were removed when that machinery was
    # reverted, so asserting them here only made the validator drift from reality.
    ci_required = [
        "name: CI",
        "on:",
        "pull_request:",
        "branches:",
        "main",
        "runs-on: ubuntu-latest",
        "actions/setup-python",
        "uv sync --group dev",
        "uv run ruff check",
        "uv run mypy",
        "uv run pytest",
    ]

    print("Validating CI/CD Workflow...")
    if validate_workflow_file(ci_path, "ci", ci_required):
        print("CI/CD Workflow is valid.")
    else:
        success = False

    release_path = ".github/workflows/release.yml"
    # The release model (ADR-0004, issue #34): CI is the single tag/publish owner,
    # firing on a merged `chore(release): vX.Y.Z` prep PR — not on a pushed tag.
    # The old tag-trigger/draft-auto-notes substrings (tags, v*, draft: true,
    # generate_release_notes) describe the removed design and are dropped.
    release_required = [
        "name: Release",
        "on:",
        "runs-on: ubuntu-latest",
        "action-gh-release",
        "chore(release): v",
        "release check",
    ]

    print("\nValidating Release Workflow...")
    if validate_workflow_file(release_path, "release", release_required):
        print("Release Workflow is valid.")
    else:
        success = False

    print("\nValidating Solomon Workflow Catalog...")
    if validate_solomon_workflow_catalog(Path.cwd()):
        print("Solomon workflow catalog is valid.")
    else:
        success = False

    if success:
        print("\nAll workflow validation checks passed successfully.")
        sys.exit(0)
    else:
        print("\nWorkflow validation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
