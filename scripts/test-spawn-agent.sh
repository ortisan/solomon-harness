#!/usr/bin/env bash

set -euo pipefail

# Test runner for scripts/spawn-agent.sh

SCRIPT_UNDER_TEST="scripts/spawn-agent.sh"

echo "Running tests for spawn-agent.sh..."

# Check if script exists and is executable
if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
    echo "Error: $SCRIPT_UNDER_TEST not found." >&2
    exit 1
fi

if [ ! -x "$SCRIPT_UNDER_TEST" ]; then
    echo "Error: $SCRIPT_UNDER_TEST is not executable." >&2
    exit 1
fi

# Test 1: Help command
echo "Test 1: Help command..."
usage_output=$("$SCRIPT_UNDER_TEST" help)
if [[ ! "$usage_output" =~ "Usage:" ]]; then
    echo "Fail: Help output did not contain 'Usage:'" >&2
    exit 1
fi
echo "Test 1 passed."

# Test 2: List command
echo "Test 2: List command..."
list_output=$("$SCRIPT_UNDER_TEST" list)
# Verify it lists at least some known agents, e.g. seo and sre
if [[ ! "$list_output" =~ "seo" || ! "$list_output" =~ "sre" ]]; then
    echo "Fail: List output did not contain 'seo' and 'sre'" >&2
    exit 1
fi
# Verify description is extracted
if [[ ! "$list_output" =~ "The Search Engine Optimization (SEO) Specialist" ]]; then
    echo "Fail: List output did not contain description for 'seo'" >&2
    exit 1
fi
echo "Test 2 passed."

# Test 3: Show command
echo "Test 3: Show command..."
show_output=$("$SCRIPT_UNDER_TEST" show seo)
if [[ ! "$show_output" =~ "# SEO Specialist Profile" ]]; then
    echo "Fail: Show output did not match expected content for seo" >&2
    exit 1
fi
echo "Test 3 passed."

# Test 4: Show non-existent agent
echo "Test 4: Show non-existent agent..."
if "$SCRIPT_UNDER_TEST" show non_existent 2>/dev/null; then
    echo "Fail: Show non_existent did not fail" >&2
    exit 1
fi
echo "Test 4 passed."

# Test 5: Invalid subcommand
echo "Test 5: Invalid subcommand..."
if "$SCRIPT_UNDER_TEST" invalid_subcommand 2>/dev/null; then
    echo "Fail: Invalid subcommand did not fail" >&2
    exit 1
fi
echo "Test 5 passed."

echo "All tests passed successfully."
