# Quick Start Guide

This guide will walk you through setting up Solomon Harness and running your first development loop.

---

## 1. Prerequisites

Before installing the harness, ensure you have the following tools installed and configured:

* **Python 3.10+** (managed easily with [uv](https://github.com/astral-sh/uv)).
* **GitHub CLI (`gh`):** Authenticated with `gh auth login`. Ensure your token has the `project` scope to allow board manipulation.
* **Host Tool:** [Claude Code](https://claude.com/claude-code) or the **Antigravity CLI (agy)** to run the agent models.
* **Docker (Optional):** Required to run the SurrealDB memory backend. The harness automatically falls back to SQLite if Docker is not running.

---

## 2. Installation

1. **Clone the repository:**
   ```bash
   git clone git@github.com:ortisan/solomon-harness.git
   cd solomon-harness
   ```

2. **Sync dependencies and virtual environment:**
   ```bash
   uv sync
   ```

3. **Install the CLI globally in editable mode:**
   ```bash
   uv pip install -e .
   ```

---

## 3. Configuration & Initialization

To configure a target repository to use Solomon Harness, navigate to your project directory and run the initialization command:

```bash
cd /path/to/your/project
solomon-harness init
```

### What `init` does:
1. Runs a system diagnostic check (doctor).
2. Copies required agent configurations (`agents/`) and automation scripts into the repository.
3. Configures local git hooks (e.g. `commit-msg`).
4. Links or creates the GitHub Project Kanban board.
5. Indexes your repository's code files into the stateful memory database.
6. Sets up the initial wiki template structure.

---

## 4. Running Your First Workflow

Once initialized, start your session inside Claude Code or the Antigravity CLI (agy). The SessionStart hook will surface current issues and state.

To start the automated workflow loop, type:

```text
/solomon-workflow
```

### Key Workflows Reference

If you want to invoke specific lifecycle stages directly, use the following commands inside your host agent session:

| Command | Action | Primary Agent |
| --- | --- | --- |
| **`/solomon-workflow`** | Scans memory and board status to run next step automatically. | Loop Engineer |
| **`/solomon-issue <description>`** | Creates a new feature issue in the Backlog. | Product Owner |
| **`/solomon-bug <description>`** | Files a bug ticket with reproduction steps in the Backlog. | QA |
| **`/solomon-refine <issue_id>`** | Refines acceptance criteria and slices tasks. | Scrum Master |
| **`/solomon-start <issue_id>`** | Starts implementation (scaffolds branch, runs TDD). | Software Engineer |
| **`/solomon-review <issue_id>`** | Performs code review and security audits on the branch. | Software Architect |
| **`/solomon-release <issue_id>`** | Merges, updates release notes, and syncs the wiki. | SRE |

> [!TIP]
> Always prefer running `/solomon-workflow`. It automatically evaluates your current board, tells you what issue is in flight, and suggests the correct subcommand to execute next.
