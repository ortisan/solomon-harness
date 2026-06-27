# Plan - Dynamic Prompt Compilation and Best Practice Injection (Task 3)

Implement dynamic best practice prompt injection based on pattern configurations defined in `.agent/config.json`.

## Scope

- In:
  - `scripts/compile-harnesses.py`
  - `tests/test_compile_harnesses.py`
- Out:
  - Any other scripts or test files.

## Design

### 1. Load Settings
The harness compiler will read `.agent/config.json` from the workspace root and parse:
- `architecture_pattern`
- `observability_pattern`
- `security_pattern`

### 2. Pattern Injection Rules
We will define mappings for affected subagents:
- **Architecture Patterns** (`architecture_pattern` value maps to template file, e.g. `"hexagonal"` -> `templates/patterns/architecture/hexagonal.md`):
  - Affected subagents: `software_architect`, `software_engineer`, `qa`, `sre`
- **Observability Patterns** (active if `observability_pattern` is `"opentelemetry"`, reads `templates/patterns/observability/opentelemetry.md`):
  - Affected subagents: `observability`, `software_engineer`, `sre`
- **Security Patterns** (active if `security_pattern` is `"secure_dev"`, reads `templates/patterns/security/secure_dev.md`):
  - Affected subagents: `security`, `software_engineer`, `qa`, `sre`

### 3. Preventing Double Appends
To prevent double appends when compiling repeatedly, we will:
- Check if the loaded agent markdown content contains a specific marker, e.g. `<!-- BEST_PRACTICES_APPENDED_START -->`.
- If the marker exists, strip everything from the marker to the end of the file.
- Strip any trailing/leading whitespace to keep formatting clean.
- Write the final compiled persona file with the marker and the appended patterns.

### 4. Logging Standards
- Ensure all compiler logs are clean, direct, and free of emojis.

## TDD Workflow Phases

### Phase 1: Red (Failing Tests)
Update `tests/test_compile_harnesses.py` to:
1. Define a config file with pattern settings.
2. Assert that `software_engineer` receives architecture, observability, and security patterns.
3. Assert that `qa` receives architecture and security patterns, but not observability.
4. Assert that `product_owner` (not affected) receives none of them.
5. Assert that running the compiler twice in a row does not accumulate duplicate appends.
6. Verify that files are correctly loaded and exceptions are handled.

Execute the test suite using `python -m unittest` to verify that the new tests fail.

### Phase 2: Green (Implementation)
Modify `scripts/compile-harnesses.py` to:
1. Load and parse `.agent/config.json`.
2. Clean the source prompt from any previously appended patterns.
3. Read the relevant pattern markdown templates.
4. Append pattern instructions to the bottom of the compiled persona file under a specific section separated by a `<!-- BEST_PRACTICES_APPENDED_START -->` marker.
5. Write the compiled content.

Execute tests and verify that they pass.

### Phase 3: Refactor
- Ensure code style is compliant with Python PEP 8 (run `ruff` format/check).
- Clean up any redundant imports or logic.

## Verification & Release
1. Run all workspace tests to verify compatibility.
2. Stage and commit changes with the message: `feat: update compiler to dynamically append best practices to agent personas`.
3. Run `scripts/wiki-sync.sh` to synchronize the project wiki.
