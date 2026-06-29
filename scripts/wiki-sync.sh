#!/usr/bin/env bash

# Wiki Synchronization Script
# Conform strictly to the Solomon Agent Setup design contract.

set -euo pipefail

# Resolve repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Ensure docs/wiki directory exists and has markdown files
WIKI_SRC_DIR="${REPO_ROOT}/docs/wiki"
if [[ ! -d "$WIKI_SRC_DIR" ]]; then
  echo "Error: Wiki source directory does not exist: $WIKI_SRC_DIR" >&2
  exit 1
fi

# Check if there are any markdown files to sync
shopt -s nullglob
MD_FILES=("$WIKI_SRC_DIR"/*.md)
shopt -u nullglob

if [[ ${#MD_FILES[@]} -eq 0 ]]; then
  echo "Error: No markdown files found in $WIKI_SRC_DIR" >&2
  exit 1
fi

# Detect git remote URL
REMOTE_URL=""
if git rev-parse --is-inside-work-tree &>/dev/null; then
  REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
fi

# If no remote is configured, enter mock mode
if [[ -z "$REMOTE_URL" ]]; then
  echo "Warning: No git remote origin found. Entering mock mode..." >&2
  
  MOCK_DIR="${REPO_ROOT}/tmp/wiki-mock-verification"
  echo "Mock Mode: Copying wiki files locally to $MOCK_DIR for verification..."
  
  rm -rf "$MOCK_DIR"
  mkdir -p "$MOCK_DIR"
  
  for file in "${MD_FILES[@]}"; do
    filename=$(basename "$file")
    cp "$file" "$MOCK_DIR/"
    echo "  Copied: $filename"
  done
  
  echo "Mock verification completed successfully."
  exit 0
fi

# Resolve wiki repository URL
# E.g., git@github.com:user/repo.git -> git@github.com:user/repo.wiki.git
# E.g., https://github.com/user/repo -> https://github.com/user/repo.wiki.git
REMOTE_URL="${REMOTE_URL%/}"
if [[ "$REMOTE_URL" =~ \.wiki\.git$ ]]; then
  WIKI_URL="$REMOTE_URL"
elif [[ "$REMOTE_URL" =~ \.wiki$ ]]; then
  WIKI_URL="${REMOTE_URL}.git"
elif [[ "$REMOTE_URL" =~ \.git$ ]]; then
  WIKI_URL="${REMOTE_URL%.git}.wiki.git"
else
  WIKI_URL="${REMOTE_URL}.wiki.git"
fi

echo "Resolved wiki remote URL: $WIKI_URL"

# Create a temporary directory in workspace
TEMP_PARENT="${REPO_ROOT}/tmp"
mkdir -p "$TEMP_PARENT"
TEMP_DIR=$(mktemp -d "${TEMP_PARENT}/wiki-sync-XXXXXX")

# Ensure cleanup on failure or exit
cleanup() {
  if [[ -d "${TEMP_DIR:-}" ]]; then
    echo "Cleaning up temporary directory..."
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT

# Clone the wiki repository
echo "Cloning wiki repository..."
INITIALIZED_FRESH=false
if ! git clone "$WIKI_URL" "$TEMP_DIR" 2>/dev/null; then
  echo "Warning: Failed to clone wiki repository from $WIKI_URL. It might be uninitialized." >&2
  echo "Attempting to initialize a fresh wiki repository locally..." >&2
  
  # Ensure TEMP_DIR exists and initialize git in it
  mkdir -p "$TEMP_DIR"
  cd "$TEMP_DIR"
  git init -b main
  git remote add origin "$WIKI_URL"
  INITIALIZED_FRESH=true
  cd "$REPO_ROOT"
fi

# Sync markdown files (flat structure)
echo "Syncing markdown files to wiki..."
for file in "${MD_FILES[@]}"; do
  cp "$file" "$TEMP_DIR/"
done

# Commit and push changes
cd "$TEMP_DIR"

# Configure local git user if not set (for git commits to succeed in CI/headless environments)
if ! git config user.name &>/dev/null; then
  git config user.name "Solomon Wiki Sync"
fi
if ! git config user.email &>/dev/null; then
  git config user.email "wiki-sync@solomon.local"
fi

git add .

# Check if there are any changes to commit
if [[ "$INITIALIZED_FRESH" = "false" ]] && git diff --quiet && git diff --staged --quiet; then
  echo "No changes detected. Wiki is already up-to-date."
  exit 0
fi

echo "Committing changes..."
git commit -m "sync: update wiki pages from repository docs"

echo "Pushing changes..."
if [[ "$INITIALIZED_FRESH" = "true" ]]; then
  if ! git push -u origin main; then
    echo "Error: Failed to push changes to initialize wiki remote" >&2
    exit 3
  fi
else
  if ! git push origin HEAD; then
    echo "Error: Failed to push changes to wiki remote" >&2
    exit 3
  fi
fi

echo "Wiki synchronized successfully."
