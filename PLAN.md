# Plan - Solomon Harness Task 4: Update CI Workflow and Verify Harness Structure Validation

This plan outlines the design, implementation, and verification steps for Task 4 of the Solomon Harness: Agent Harness Refactoring plan.

## Requirements

1. **Update `.github/workflows/ci.yml`**:
   - Add a step to run python unit tests:
     ```yaml
     - name: Run python unit tests
       run: |
         python3 -m unittest discover -s tests
     ```
   - Add a step to run the individual agent harness evaluation suites dynamically:
     ```yaml
     - name: Run individual agent harness evaluations
       run: |
         for agent_dir in agents/*; do
           if [ -d "$agent_dir" ] && [ -f "$agent_dir/main.py" ]; then
             echo "Running evaluations for $(basename "$agent_dir")..."
             python3 "$agent_dir/main.py" eval
           fi
         done
     ```
   - Update script syntax validation checks to include the new python scripts: `scripts/compile-harnesses.py`, `scripts/validate-agents.py`, `scripts/validate-templates.py`, and `scripts/validate-workflows.py`.

2. **Run Validation and Verification Checks**:
   - Ensure the modified CI workflow validates successfully against `scripts/validate-workflows.py`.
   - Run the unit tests and dynamic agent evaluations locally to confirm they all pass.

3. **Git Commit**:
   - Stage all changes and commit with the exact message: `test: update CI workflow and verify harness structure validation`.

## TDD Development Cycle

### 1. Red Phase
- Modify `scripts/validate-workflows.py` to include the new required substrings for the CI workflow:
  - `"python3 -m unittest discover -s tests"`
  - `"python3 \"$agent_dir/main.py\" eval"`
- Run `python3 scripts/validate-workflows.py` and confirm that it fails because the CI workflow does not yet contain these steps.

### 2. Green Phase
- Edit `.github/workflows/ci.yml` to:
  - Add the "Run python unit tests" step.
  - Add the "Run individual agent harness evaluations" step.
  - Update the "Check python script syntax" step to include all the new python scripts.
- Run `python3 scripts/validate-workflows.py` and confirm that it passes successfully.

### 3. Refactor Phase
- Review the formatting of the modified YAML file.
- Verify that there are no style issues, trailing whitespaces, or tab character violations.
- Run the python unit tests and evaluations locally one final time to verify correctness.
- Sync the project wiki using the `scripts/wiki-sync.sh` script if applicable.
