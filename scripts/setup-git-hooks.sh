#!/bin/bash

# Setup Git Hooks script
git_dir=$(git rev-parse --git-dir 2>/dev/null)

if [ -z "$git_dir" ]; then
  echo "Error: Not a git repository."
  exit 1
fi

echo "Installing Solomon Harness Git Hooks..."

hooks_src="scripts/git-hooks"
hooks_dest="$git_dir/hooks"

mkdir -p "$hooks_dest"

# Copy hooks
if [ -f "$hooks_src/commit-msg" ]; then
  cp "$hooks_src/commit-msg" "$hooks_dest/commit-msg"
  chmod +x "$hooks_dest/commit-msg"
  echo "Installed commit-msg hook."
fi

if [ -f "$hooks_src/pre-commit" ]; then
  cp "$hooks_src/pre-commit" "$hooks_dest/pre-commit"
  chmod +x "$hooks_dest/pre-commit"
  echo "Installed pre-commit hook."
fi

echo "Git hooks installed successfully!"
