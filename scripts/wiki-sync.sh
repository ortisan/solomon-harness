#!/usr/bin/env bash

# Wiki Synchronization Script
# Conform strictly to the Solomon Agent Setup design contract.

set -euo pipefail

# Keep the immutable harness runtime separate from the consumer repository.
# In an installed project this script lives under `.agents/solomon/scripts`,
# while wiki content, Git remotes, and temporary output remain project-owned at
# the outer worktree root.
HARNESS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(git -C "$HARNESS_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$PROJECT_ROOT" ]]; then
  PROJECT_ROOT="$HARNESS_ROOT"
fi

# Ensure docs/wiki directory exists and has markdown files
WIKI_SRC_DIR="${PROJECT_ROOT}/docs/wiki"
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
if git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
  REMOTE_URL=$(git -C "$PROJECT_ROOT" config --get remote.origin.url 2>/dev/null || true)
fi

# If no remote is configured, enter mock mode
if [[ -z "$REMOTE_URL" ]]; then
  echo "Warning: No git remote origin found. Entering mock mode..." >&2
  
  MOCK_DIR="${PROJECT_ROOT}/tmp/wiki-mock-verification"
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

# Strip any user:secret@ userinfo from a URL before echoing it, so a token
# embedded in a remote cannot leak into the logs. Leaves scp-style git@host:path
# remotes (no `//`) untouched, since that user is not a secret.
strip_userinfo() {
  local url="$1"
  if [[ "$url" == *"://"* ]]; then
    local scheme="${url%%://*}"
    local rest="${url#*://}"
    local authority="${rest%%/*}"
    local path="${rest#"$authority"}"
    [[ "$authority" == *"@"* ]] && authority="${authority##*@}"
    printf '%s' "${scheme}://${authority}${path}"
  else
    printf '%s' "$url"
  fi
}

echo "Resolved wiki remote URL: $(strip_userinfo "$WIKI_URL")"

# --- Wiki initialization detection (no-browser degrade floor, issue #117) ------
# GitHub creates the <repo>.wiki.git content repo only after the first wiki page
# is saved through the web UI, and exposes no API for that first page. Detection
# -- the ls-remote ref probe, its ~10s timeout, the actionable message, and the
# exit code -- lives in solomon_harness.wiki_bootstrap so the harness and this
# script share one source; call it here rather than re-deriving it. It runs no
# browser action and never blocks on input, so a headless or CI invocation
# degrades deterministically with exit 4 and surfaces no raw git error. The
# timeout is read from WIKI_SYNC_LSREMOTE_TIMEOUT. Run the bundled package from
# its own frozen uv project and isolated Python mode: neither the consumer cwd,
# PYTHONPATH, user-site packages, nor a consumer sitecustomize can shadow the
# immutable harness runtime.
if [[ "$HARNESS_ROOT" == */.agents/solomon ]]; then
  HARNESS_VENV="$HARNESS_ROOT/state/venv"
else
  HARNESS_VENV="$HARNESS_ROOT/.agents/solomon/state/venv"
fi
set +e
(
  cd "$HARNESS_ROOT"
  env -u PYTHONHOME -u PYTHONPATH \
    UV_NO_CONFIG=1 \
    UV_PROJECT_ENVIRONMENT="$HARNESS_VENV" \
    uv run --frozen --project "$HARNESS_ROOT" \
    python -I -m solomon_harness.wiki_bootstrap detect "$REMOTE_URL"
)
DETECT_STATUS=$?
set -e
if [[ "$DETECT_STATUS" -ne 0 ]]; then
  exit "$DETECT_STATUS"
fi

echo "Wiki content repository detected. Proceeding to sync."

# Create a temporary directory in workspace
TEMP_PARENT="${PROJECT_ROOT}/tmp"
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

# Clone the wiki repository. Detection above already exited 4 on an uninitialized
# wiki, so the remote is known to carry refs here; a clone failure is a genuine
# error (network or permissions), not an uninitialized wiki, so there is no
# local-init-then-push fallback to attempt.
echo "Cloning wiki repository..."
if ! git clone "$WIKI_URL" "$TEMP_DIR" 2>/dev/null; then
  echo "Error: Failed to clone the wiki repository." >&2
  exit 3
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
