#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Solomon Agent Bootstrap ==="

# 1. Extract project metadata
echo "Extracting project metadata..."

PROJECT_NAME=""
if [ -f "package.json" ]; then
    # Extract name from package.json
    PROJECT_NAME=$(python3 -c "import json; print(json.load(open('package.json')).get('name', ''))" 2>/dev/null || true)
fi

if [ -z "$PROJECT_NAME" ] && [ -f "pubspec.yaml" ]; then
    # Extract name from pubspec.yaml
    PROJECT_NAME=$(grep -m1 '^name:' pubspec.yaml | cut -d: -f2 | tr -d ' ' 2>/dev/null || true)
fi

if [ -z "$PROJECT_NAME" ] && [ -f "pyproject.toml" ]; then
    # Extract name from pyproject.toml
    PROJECT_NAME=$(python3 -c "import tomli as toml; print(toml.load(open('pyproject.toml', 'rb')).get('project', {}).get('name', ''))" 2>/dev/null || \
                   python3 -c "import tomllib as toml; print(toml.load(open('pyproject.toml', 'rb')).get('project', {}).get('name', ''))" 2>/dev/null || \
                   grep -m1 '^name =' pyproject.toml | cut -d= -f2 | tr -d '"'\'' ' 2>/dev/null || true)
fi

if [ -z "$PROJECT_NAME" ]; then
    PROJECT_NAME=$(basename "$PWD")
fi

GIT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "none")

# Scan for technologies
TECH_LIST=()
if [ -f "pubspec.yaml" ] || [ -f "pubspec.lock" ] || [ -d ".dart_tool" ] || find . -maxdepth 3 -name "*.dart" -print -quit | grep -q .; then
    TECH_LIST+=("Dart")
fi
if [ -f "package.json" ] || [ -f "tsconfig.json" ] || [ -d "node_modules" ] || find . -maxdepth 3 -name "*.js" -o -name "*.ts" -print -quit | grep -q .; then
    TECH_LIST+=("JavaScript/TypeScript")
fi
if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ] || find . -maxdepth 3 -name "*.py" -print -quit | grep -q .; then
    TECH_LIST+=("Python")
fi
if [ -f "Cargo.toml" ] || [ -f "Cargo.lock" ]; then
    TECH_LIST+=("Rust")
fi
if [ -f "go.mod" ]; then
    TECH_LIST+=("Go")
fi
if [ -f "Gemfile" ] || [ -f "Gemfile.lock" ]; then
    TECH_LIST+=("Ruby")
fi
if [ -f "build.gradle" ] || [ -f "pom.xml" ]; then
    TECH_LIST+=("Java/Kotlin")
fi

if [ ${#TECH_LIST[@]} -eq 0 ]; then
    TECH_LIST+=("Generic/Shell")
fi

# Join technology list with ", "
TECHNOLOGIES=$(printf ", %s" "${TECH_LIST[@]}")
TECHNOLOGIES=${TECHNOLOGIES:2}

GENERATION_DATE=$(date "+%Y-%m-%d %H:%M:%S")

echo "  - Project Name: $PROJECT_NAME"
echo "  - Git Remote:   $GIT_REMOTE"
echo "  - Technologies: $TECHNOLOGIES"

# 2. Generate .claude/settings.json
echo "Generating .claude/settings.json..."
mkdir -p .claude
cat <<EOT > .claude/settings.json
{
  "\$schema": "https://raw.githubusercontent.com/anthropic-cookbook/claude-code/main/schema/settings.schema.json",
  "model": "claude-3-5-sonnet-latest",
  "watch": true,
  "permissions": {
    "allow": [
      "git status",
      "git diff",
      "git log"
    ],
    "ask": [
      "git commit",
      "git push"
    ]
  }
}
EOT

# 3. Generate .agents/skills.json
echo "Generating .agents/skills.json..."
mkdir -p .agents
cat <<EOT > .agents/skills.json
{
  "entries": [
    { "path": ".agents/skills" }
  ],
  "inherits": [],
  "exclude": []
}
EOT

# 4. Assemble core workspace rule files CLAUDE.md and .agents/AGENTS.md
interpolate_and_write() {
    local template_path="$1"
    local dest_path="$2"
    local fallback_content="$3"

    if [ -f "$template_path" ]; then
        echo "Interpolating $template_path into $dest_path..."
        PROJECT_NAME="$PROJECT_NAME" GIT_REMOTE="$GIT_REMOTE" TECHNOLOGIES="$TECHNOLOGIES" GENERATION_DATE="$GENERATION_DATE" python3 -c "
import os
template_path = '$template_path'
dest_path = '$dest_path'

with open(template_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('{{PROJECT_NAME}}', os.environ.get('PROJECT_NAME', ''))
content = content.replace('{{GIT_REMOTE}}', os.environ.get('GIT_REMOTE', ''))
content = content.replace('{{TECHNOLOGIES}}', os.environ.get('TECHNOLOGIES', ''))
content = content.replace('{{TECH_STACK}}', os.environ.get('TECHNOLOGIES', ''))
content = content.replace('{{GENERATION_DATE}}', os.environ.get('GENERATION_DATE', ''))

dir_name = os.path.dirname(dest_path)
if dir_name:
    os.makedirs(dir_name, exist_ok=True)
with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)
"
    else
        echo "Template $template_path not found. Writing generic placeholder to $dest_path..."
        echo "$fallback_content" > "$dest_path"
    fi
}

CLAUDE_FALLBACK="# $PROJECT_NAME - Workspace Rules

## Metadata
- **Project Name:** $PROJECT_NAME
- **Git Remote:** $GIT_REMOTE
- **Technologies:** $TECHNOLOGIES
- **Generated:** $GENERATION_DATE

## Assistant Guidelines
- Always conform to the Development Workflow.
- Ensure all commits pass the commit-msg git hook (Conventional Commits, no emojis).
- Keep code clean, test-driven (TDD), and well-documented."

AGENTS_FALLBACK="# $PROJECT_NAME - Agent Customizations

## Profile
- **Project Name:** $PROJECT_NAME
- **Core Stack:** $TECHNOLOGIES
- **Repository:** $GIT_REMOTE

## Customization Rules
- Before starting any implementation, always write a PLAN.md.
- Follow TDD cycles: Red, Green, Refactor.
- Sync the documentation/wiki using scripts/wiki-sync.sh upon releases."

interpolate_and_write "templates/CLAUDE.md.template" "CLAUDE.md" "$CLAUDE_FALLBACK"
interpolate_and_write "templates/AGENTS.md.template" "agents/AGENTS.md" "$AGENTS_FALLBACK"

# 5. Install Git commit-msg hook
echo "Installing Git commit-msg hook..."
HOOKS_DIR=$(git rev-parse --git-path hooks 2>/dev/null || echo ".git/hooks")
if [ -n "$HOOKS_DIR" ]; then
    mkdir -p "$HOOKS_DIR"
    cp scripts/git-hooks/commit-msg "$HOOKS_DIR/commit-msg"
    chmod +x "$HOOKS_DIR/commit-msg"
    echo "  Hook installed to $HOOKS_DIR/commit-msg"
else
    echo "  Warning: Git hooks directory could not be resolved. Commit hook was not installed."
fi

# 6. Sync agent configurations and rules
echo "Syncing agent configurations and rules..."
mkdir -p .agents/agents
ln -sf ../agents/AGENTS.md .agents/AGENTS.md
for f in agents/*.md; do
    filename=$(basename "$f")
    if [ "$filename" != "AGENTS.md" ]; then
        ln -sf "../../agents/$filename" ".agents/agents/$filename"
    fi
done

echo "=== Bootstrap Completed Successfully ==="
