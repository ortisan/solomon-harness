#!/usr/bin/env python3
import sys
import os
import re
import unicodedata

def has_emoji(text):
    for char in text:
        cp = ord(char)
        # Check standard emoji / symbol blocks
        is_emoji = (0x1F000 <= cp <= 0x1FFFF) or (0x2600 <= cp <= 0x27BF) or (0x2300 <= cp <= 0x23FF)
        if not is_emoji:
            try:
                cat = unicodedata.category(char)
                if cat == 'So':  # Symbol, other
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
    lines = content.split('\n')
    for idx, line in enumerate(lines, 1):
        # YAML files must not use tabs for indentation
        if '\t' in line:
            print(f"Error [{filepath}:{idx}]: Contains tab characters. YAML requires spaces for indentation.")
            return False
        
        # Check for trailing spaces or basic syntax errors
        # E.g., colon must be followed by space or newline
        if ':' in line:
            # simple check: if colon is not inside quotes, it should have space after it
            # We can do a basic check for key:value without space
            parts = line.split(':')
            if len(parts) > 1:
                key = parts[0]
                val = ':'.join(parts[1:])
                # Check if it looks like a key:value pair (not a URL)
                if not (key.strip().startswith('http') or key.strip().startswith('git@') or val.startswith('//')):
                    if val and not val.startswith(' ') and not val.startswith('\n') and not val.strip() == '':
                        print(f"Error [{filepath}:{idx}]: Missing space after colon in key-value pair.")
                        return False

    # Check matching quotes and brackets
    # Using stack for brackets/braces
    stack = []
    brackets_map = {']': '[', '}': '{'}
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for idx, char in enumerate(content):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote:
            if char in brackets_map.values():
                stack.append(char)
            elif char in brackets_map.keys():
                if not stack or stack[-1] != brackets_map[char]:
                    print(f"Error [{filepath}]: Mismatched brackets or braces.")
                    return False
                stack.pop()

    if in_single_quote or in_double_quote:
        print(f"Error [{filepath}]: Unclosed quote character.")
        return False
    if stack:
        print(f"Error [{filepath}]: Unclosed brackets or braces.")
        return False

    return True

def validate_workflow_file(filepath, name_pattern, required_substrings):
    if not os.path.exists(filepath):
        print(f"Error: Workflow file does not exist: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not content.strip():
        print(f"Error: Workflow file is empty: {filepath}")
        return False

    # Emoji Check
    emoji_found, char = has_emoji(content)
    if emoji_found:
        print(f"Error: Emoji or icon '{char}' found in {filepath}. Emojis are strictly prohibited.")
        return False

    # Formatting Check
    if not validate_yaml_formatting(content, filepath):
        return False

    # Security Check: Explicit permissions and Pinned actions (SHAs)
    has_permissions_block = False
    lines = content.split('\n')
    for idx, line in enumerate(lines, 1):
        if 'permissions:' in line:
            has_permissions_block = True
        
        # Match uses: actions/checkout@v4 or uses: actions/checkout@sha
        uses_match = re.search(r'uses:\s*([^\s#]+)', line)
        if uses_match:
            action_ref = uses_match.group(1)
            # Skip local actions (starting with ./)
            if not action_ref.startswith('./'):
                if '@' not in action_ref:
                    print(f"Error [{filepath}:{idx}]: Action '{action_ref}' is not pinned to a version/SHA.")
                    return False
                parts = action_ref.split('@')
                sha = parts[1]
                # SHA must be a 40-character hex string
                if not re.match(r'^[a-fA-F0-9]{40}$', sha):
                    print(f"Error [{filepath}:{idx}]: Action '{action_ref}' must be pinned to a 40-character commit SHA for security.")
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
    ci_required = [
        "name: CI",
        "on:",
        "push:",
        "pull_request:",
        "branches:",
        "main",
        "runs-on: ubuntu-latest",
        "actions/setup-python",
        "bash -n",
        "python3 -m py_compile",
        "shellcheck",
        "bootstrap-agent.sh",
        "python3 -m unittest discover -s tests",
        "python3 \"$agent_dir/main.py\" eval",
        "scripts/compile-harnesses.py",
        "scripts/validate-agents.py",
        "scripts/validate-templates.py",
        "scripts/validate-workflows.py"
    ]

    print("Validating CI/CD Workflow...")
    if validate_workflow_file(ci_path, "ci", ci_required):
        print("CI/CD Workflow is valid.")
    else:
        success = False

    release_path = ".github/workflows/release.yml"
    release_required = [
        "name: Release",
        "on:",
        "push:",
        "tags:",
        "v*",
        "runs-on: ubuntu-latest",
        "action-gh-release",
        "draft: true",
        "generate_release_notes: true"
    ]

    print("\nValidating Release Workflow...")
    if validate_workflow_file(release_path, "release", release_required):
        print("Release Workflow is valid.")
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
