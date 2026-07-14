# Harness Commands Reference

This document provides a detailed reference of all custom slash commands (`/solomon-*`) available in the **solomon-harness** harness. These commands automate SDLC transitions, move board cards, manage Git worktrees, and trigger specialized AI agents.

---

## 1. Lifecycle Commands

### `/solomon-workflow` (End-to-End Orchestrator)
Runs a task end-to-end, or continues from a previous execution. It scans the repository's current state, checked-out branch, open issues, and board status to determine where development stopped, then proposes or automatically runs the next logical step.
* **Arguments:** Optional focus (e.g., issue or PR number).
* **Primary Agent:** Orchestrator (hierarchical coordinator).
* **Workflows:**
  1. Checks for approved PRs to trigger release.
  2. Checks for open PRs needing review to trigger review.
  3. Checks for in-progress branches to resume coding.
  4. Checks for ready issues to start implementation.
  5. Provides a choice between a **Single Step** execution or **Autonomous Mode** (looping through tasks until blocked by human gates).

### `/solomon-loop` (Autonomous Parallel Loop)
Runs the fully autonomous parallel loop: it spawns multiple worker agents that start, develop, test, review, and open draft PRs for Ready issues concurrently.
* **Arguments:** Optional `--issues 42,43` to restrict the run to specific issues.
* **Primary Agent:** Orchestrator (delegates to `software_engineer`, `qa`, `software_architect` workers).
* **Workflows:**
  1. Asks for the concurrency limit (default: 3).
  2. Runs `solomon-harness dev loop --concurrency <limit>` under the single-driver lock.
  3. Each worker claims one Ready issue, implements it with TDD in an isolated worktree, and opens a draft PR.
  4. Human review remains the merge gate; the loop never merges its own PRs.

### `/solomon-start` (Developer Center)
Begins implementation on a `Ready` issue.
* **Arguments:** `<issue_number>`
* **Primary Agents:** `scrum_master`, `software_architect`, `software_engineer`
* **Workflows:**
  1. Spins up a clean, isolated **Git Worktree** under `<repo>-worktrees/` to keep your main branch checkout clean.
  2. Sets card status to `In Progress` and links the branch back to the issue.
  3. Scaffolds a `PLAN.md` file in the worktree detailing changes, target files, and test plans.
  4. Runs TDD implementation loops, prompting for verification at each checkpoint.

### `/solomon-refine` (Backlog Grooming)
Refines a backlog issue to `Ready` status.
* **Arguments:** `<issue_number>`
* **Primary Agent:** `scrum_master`
* **Workflows:**
  1. Validates the issue against the **Definition of Ready (DoR)**.
  2. Slices complex issues into smaller, manageable sub-tasks.
  3. Updates requirements, estimates difficulty, and moves the card to `Ready`.

### `/solomon-review` (Quality Assurance & Audit)
Performs code review, quality audits, and security checks on a Pull Request.
* **Arguments:** `<pr_number>`
* **Primary Agent:** `software_architect`
* **Workflows:**
  1. Analyzes the diff for architectural adherence and security vulnerabilities (STRIDE).
  2. Validates test coverage and ensures the test suite passes.
  3. Automatically posts comments with feedback, or approves/merges the PR if compliant.

### `/solomon-release` (SRE Deployment)
Triggers production release preparation and wiki documentation sync.
* **Arguments:** `<pr_number>`
* **Primary Agent:** `sre` (Site Reliability Engineer)
* **Workflows:**
  1. Verifies that the milestone is fully complete (0 open issues).
  2. Updates `CHANGELOG.md` and bumps the package version based on Conventional Commits.
  3. Appends version entries to **[Delivered Issues Log](Delivered)** (with clickable GitHub issue and PR links).
  4. Runs `scripts/wiki-sync.sh` to update the remote GitHub Wiki.

---

## 2. Issue Capture Commands

### `/solomon-idea` (Product Discovery)
Captures early feature ideas or improvements without cluttering the active board.
* **Arguments:** `<title_or_description>`
* **Primary Agent:** `product_owner`
* **Workflows:** Inserts cards into the `Ideas` column for future refinement.

### `/solomon-issue` (Feature Story)
Creates a detailed, structured user story directly in the backlog.
* **Arguments:** `<title_or_description>`
* **Primary Agent:** `product_owner`
* **Workflows:** Runs the elicitation gate first (six readiness criteria; a vague demand gets at most 3 rounds of Socratic questions, a complete one skips straight to shaping), compiles structured acceptance criteria, and creates the GitHub issue in `Backlog`.

### `/solomon-bug` (Bug Reporter)
Files a structured bug ticket with detailed reproduction steps.
* **Arguments:** `<title_or_description>`
* **Primary Agent:** `qa`
* **Workflows:** Extracts OS details, logs, and environments to create a structured bug card in `Backlog`.

---

## 3. Analysis & Compliance Commands

### `/solomon-scan-arch` (Architecture Scan)
Performs codebase structure scanning against defined module boundaries.
* **Arguments:** None.
* **Primary Agent:** `software_architect`
* **Workflows:** Scans imports and component definitions to detect boundary bleed, writing reports to project memory.

### `/solomon-scan-dedup` (Code Deduplication)
Identifies redundant or duplicated code blocks to suggest clean abstractions.
* **Arguments:** None.
* **Primary Agent:** `software_engineer`
* **Workflows:** Scans files to flag duplicate logic, writing refactoring proposals for DRY compliance.
