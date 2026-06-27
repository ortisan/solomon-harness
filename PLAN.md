# Plan - Implement Interactive Configuration Selection in Bootstrap Script

Update scripts/bootstrap-agent.sh to support interactive and non-interactive choice selection for architecture, observability, and security patterns, saving the choices to .agent/config.json.

## Scope

- In:
  - scripts/bootstrap-agent.sh
  - tests/test_bootstrap.py (new test file for TDD)
- Out:
  - Modifying files unrelated to agent bootstrapping or configuration.

## Action Items

- [ ] Write a new test suite tests/test_bootstrap.py to test the bootstrap configuration functionality (TDD - Red Phase).
  - Verify that running bootstrap-agent.sh in non-interactive mode correctly writes default configuration patterns.
  - Verify that existing keys in .agent/config.json (e.g., models, timeout_seconds, max_retries, database) are preserved.
- [ ] Run the test suite and verify that the tests fail.
- [ ] Update scripts/bootstrap-agent.sh:
  - Add logic to parse --non-interactive command line flag or detect NON_INTERACTIVE=true environment variable.
  - If in non-interactive mode:
    - Automatically select default patterns: architecture_pattern = hexagonal, observability_pattern = opentelemetry, security_pattern = secure_dev.
  - If in interactive mode:
    - Prompt the developer in Portuguese using bash read prompts for selecting architecture, observability, and security.
    - Map the choice selections to clean/functional/hexagonal, opentelemetry/basic, secure_dev/standard.
  - Save the mapped configuration choices to .agent/config.json, merging them into any existing JSON content to preserve existing keys.
  - Ensure the script exits with 0 on success and a non-zero exit code on failure.
  - Do not use emojis in output messages.
- [ ] Run the test suite to ensure the new logic passes the tests (TDD - Green Phase).
- [ ] Refactor scripts/bootstrap-agent.sh if needed to optimize readability and robustness (TDD - Refactor Phase).
- [ ] Test the script manually in both interactive (via simulated inputs) and non-interactive modes.
- [ ] Run scripts/wiki-sync.sh to sync the project wiki.
- [ ] Stage and commit the changes to Git.

## Open Questions

None
