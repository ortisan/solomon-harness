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

# --- Wiki initialization detection (no-browser degrade floor, issue #117) ------
# GitHub creates the <repo>.wiki.git content repo only after the first wiki page
# is saved through the web UI, and exposes no API for that first page. Probe the
# remote for refs under a short timeout BEFORE any clone or push. This is the
# observable gate: an uninitialized wiki must terminate in an actionable message,
# never a raw clone/push error. The probe runs no browser action and never blocks
# on input, so a headless or CI invocation degrades deterministically.
WIKI_LSREMOTE_TIMEOUT="${WIKI_SYNC_LSREMOTE_TIMEOUT:-10}"

# Derive the human web URL of the first-page editor the operator must open. Work
# from the repo remote (not the .wiki.git form) and normalize the common SSH and
# https shapes to an https URL.
WEB_REPO="${REMOTE_URL%.git}"
if [[ "$WEB_REPO" =~ ^git@([^:]+):(.+)$ ]]; then
  WEB_REPO="https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
elif [[ "$WEB_REPO" =~ ^ssh://git@(.+)$ ]]; then
  WEB_REPO="https://${BASH_REMATCH[1]}"
fi
WIKI_NEW_URL="${WEB_REPO}/wiki/_new"

# Resolve a portable timeout wrapper: GNU coreutils `timeout` or homebrew
# `gtimeout`. Without one the probe cannot be bounded, so detection is treated as
# inconclusive below rather than risking an indefinite hang.
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
fi

# Probe for heads. Capture the status without tripping `set -e`, and suppress git
# stderr so a raw remote error never reaches the operator on this path.
set +e
if [[ -n "$TIMEOUT_BIN" ]]; then
  WIKI_REFS=$("$TIMEOUT_BIN" "$WIKI_LSREMOTE_TIMEOUT" git ls-remote --heads "$WIKI_URL" 2>/dev/null)
  LSREMOTE_STATUS=$?
else
  WIKI_REFS=""
  LSREMOTE_STATUS=124
fi
set -e

if [[ -z "$WIKI_REFS" ]]; then
  echo "Error: the GitHub wiki has not been initialized." >&2
  echo "GitHub creates the wiki content repository ($WIKI_URL) only after the" >&2
  echo "first page is saved through the web UI, and exposes no API for that page." >&2
  echo "Initialize it once: open" >&2
  echo "  ${WIKI_NEW_URL}" >&2
  echo "and save a page (any content), then re-run the wiki step to publish docs." >&2
  exit 4
fi

echo "Wiki content repository detected. Proceeding to sync."

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
if ! git clone "$WIKI_URL" "$TEMP_DIR"; then
  echo "Error: Failed to clone wiki repository from $WIKI_URL" >&2
  exit 2
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
if git diff --quiet && git diff --staged --quiet; then
  echo "No changes detected. Wiki is already up-to-date."
  exit 0
fi

echo "Committing changes..."
git commit -m "sync: update wiki pages from repository docs"

echo "Pushing changes..."
if ! git push origin HEAD; then
  echo "Error: Failed to push changes to wiki remote" >&2
  exit 3
fi

echo "Wiki synchronized successfully."
