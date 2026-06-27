# Plan - Initialize Agent Harness Directory Structure and Configuration

This plan outlines the design, implementation, and verification steps for Task 1 of the Solomon Harness: Agent Harness Refactoring.

## Requirements

1. Create directories:
   - `.agent/`
   - `agents/`
   - `skills/`
   - `tools/`
   - `memory/`
   - `memory/short_term/`
   - `memory/long_term/`
   - `tests/`

2. Create `.agent/config.json` containing:
   - Default, reasoning, and embedding models.
   - Timeout and max retries parameters.
   - Clean JSON formatting, in English, without emojis.

3. Create `.agent/secure_vault.enc` containing:
   - Base64-encoded representation of a mock JSON vault (`eyJhbnRocm9waWNfYXBpX2tleSI6ICJtb2NrX2tleSJ9`).

4. Update `.gitignore` to append rules for:
   - `memory/long_term/harness.db`
   - `memory/short_term/*.json`
   - `.agent/secure_vault.enc`

5. Stage and commit changes with the message:
   - `chore: initialize agent harness directory structure and configuration files`

## TDD and Verification Steps

A Python script `tests/test_harness_init.py` will be created using the standard library `unittest` to drive the test-driven development loop.

1. **Red Stage**:
   - Create `tests/` directory if needed and write `tests/test_harness_init.py` before implementing any other directories or configurations.
   - Run the test script using `python3 -m unittest tests/test_harness_init.py` and confirm it fails.

2. **Green Stage**:
   - Create the required directories.
   - Create `.agent/config.json` with the required parameters.
   - Create `.agent/secure_vault.enc` with the specified base64 string.
   - Update `.gitignore` with the rules.
   - Run `python3 -m unittest tests/test_harness_init.py` and confirm it passes.

3. **Refactor Stage**:
   - Ensure file formatting is correct and files are clean.
   - Stage all changes, commit them, and execute `scripts/wiki-sync.sh` to sync the wiki.

## Execution Checklist

- [x] Create `tests/test_harness_init.py` (TDD Red).
- [x] Run the tests to verify failures (Red).
- [x] Create directories: `.agent/`, `agents/`, `skills/`, `tools/`, `memory/`, `memory/short_term/`, `memory/long_term/`.
- [x] Create `.agent/config.json`.
- [x] Create `.agent/secure_vault.enc`.
- [x] Update `.gitignore`.
- [x] Run the tests to verify success (Green).
- [x] Stage changes and commit with the specified message.
- [x] Execute `scripts/wiki-sync.sh` to sync the project wiki.

