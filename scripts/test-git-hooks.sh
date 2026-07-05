#!/usr/bin/env bash

set -euo pipefail

# Test runner for scripts/git-hooks/pre-commit and scripts/git-hooks/commit-msg.
#
# These hooks shell out to external interpreters (uv, python3). This suite
# checks that a missing prerequisite fails fast with an actionable message
# instead of a bare "command not found" error.

PRE_COMMIT="scripts/git-hooks/pre-commit"
COMMIT_MSG="scripts/git-hooks/commit-msg"

echo "Running tests for scripts/git-hooks..."

# Check the hooks exist and are executable
for hook in "$PRE_COMMIT" "$COMMIT_MSG"; do
    if [ ! -f "$hook" ]; then
        echo "Error: $hook not found." >&2
        exit 1
    fi
    if [ ! -x "$hook" ]; then
        echo "Error: $hook is not executable." >&2
        exit 1
    fi
done

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# Test 1: pre-commit with no "uv" on PATH fails with an actionable message,
# not a bare "command not found".
echo "Test 1: pre-commit without uv on PATH..."
# A minimal PATH containing only the plain POSIX utilities the hook itself
# needs (sh builtins + command), with no uv anywhere on it.
output="$(PATH="/usr/bin:/bin" sh "$PRE_COMMIT" 2>&1)" && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then
    echo "Fail: pre-commit should have exited non-zero without uv on PATH" >&2
    exit 1
fi
if [[ "$output" == *"command not found"* ]]; then
    echo "Fail: pre-commit fell through to a bare 'command not found' error instead of guarding:" >&2
    echo "$output" >&2
    exit 1
fi
if [[ "$output" != *"uv"* ]] || [[ "$output" != *"https://github.com/astral-sh/uv"* ]]; then
    echo "Fail: pre-commit did not print an actionable uv install hint:" >&2
    echo "$output" >&2
    exit 1
fi
echo "Test 1 passed."

# Test 2: the guard itself does not false-positive when uv is present. Run
# just the hook's own guard block (extracted verbatim from the real file) so
# this stays fast and does not require running the full validation loop.
echo "Test 2: pre-commit guard does not trip when uv is present..."
guard_snippet="$(awk '/^command -v uv/,/^}/' "$PRE_COMMIT")"
if [ -z "$guard_snippet" ]; then
    echo "Fail: could not locate the uv prerequisite guard in $PRE_COMMIT" >&2
    exit 1
fi
guard_script="$WORKDIR/guard-only.sh"
{
    echo "#!/bin/sh"
    echo "$guard_snippet"
    echo "echo GUARD_PASSED"
} > "$guard_script"
chmod +x "$guard_script"

if command -v uv >/dev/null 2>&1; then
    guard_output="$(sh "$guard_script")"
    if [[ "$guard_output" != "GUARD_PASSED" ]]; then
        echo "Fail: guard tripped even though uv is on PATH: $guard_output" >&2
        exit 1
    fi
    echo "Test 2 passed."
else
    echo "Skipping test 2: uv is not installed in this environment."
fi

echo "All tests passed successfully."
