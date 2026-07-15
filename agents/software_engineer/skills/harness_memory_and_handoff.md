---
name: harness-memory-and-handoff
description: Governs when and how to write save_decision, log_issue, save_session, and log_handoff records to the harness's SurrealDB-backed project memory so the next agent resumes from state rather than the diff. Use when a non-obvious design choice is made, a defect is found out of scope, a long task needs a checkpoint, or work is ready to hand off to qa.
---

# Harness Memory and Handoff

Persist the reasoning and state of your work to the project memory so the next agent resumes from a record, not from re-reading the diff. The discipline: capture non-obvious design choices with `save_decision`, file discovered defects with `log_issue`, checkpoint long tasks with `save_session`, and close out with a `log_handoff` to `qa` that points at a written verification contract. Memory is the continuity layer; if a fact is not in it, the next agent does not have it.

## Where memory lives and how you reach it

The store is SurrealDB-primary with a SQLite fallback (`solomon_harness/tools/database_client.py`); backend and credentials come from `.agents/solomon/config/project.json`. Reach it two ways: the `solomon-memory` MCP server (registered in `.mcp.json`), which exposes each operation as a tool you call directly, or `DatabaseClient(harness_dir=...)` from code. Prefer the MCP tools during a work session; reserve `DatabaseClient` for scripts and tests. The write tools are append-or-upsert and never block your task on failure of the store, so treat a write error as a logged warning, not a crash, but do verify the write landed before you rely on it for resume.

## save_decision — the non-obvious choices

`save_decision(title, rationale, outcome, author, branch="main", commit_sha="")`. This is an ADR-style row. Write one when a reviewer would ask "why did you do it this way" and the answer is not self-evident from the code: a library or pattern selection, a deliberate deviation from a sibling skill's default (for example choosing a different error shape than `error_handling_and_problem_details` prescribes), a performance/correctness tradeoff, a workaround for an upstream bug, or a boundary you drew in `hexagonal_architecture_ports_and_adapters`.

- `rationale` must state the context, the alternatives you considered, and why you rejected them. A decision without rejected alternatives is a note, not a decision.
- `outcome` is the choice itself in one line, plus its consequence (what it constrains downstream).
- `author` is your agent name (`software_engineer`); `branch` is the current `feature/*` or `bugfix/*` branch from `git_flow_and_conventional_commits`; fill `commit_sha` after you commit so the decision is anchored to the code that realizes it.
- Do not log mechanical or obvious choices (naming, formatting, applying TDD). Noise dilutes the record. Aim for the handful of choices per task that future-you would have to reverse-engineer.

## log_issue — defects you discover but do not fix here

`log_issue(github_id, title, type_, status, milestone_id=None)`. When you find a defect outside your current scope, file it instead of silently fixing it (scope creep breaks the TDD trail) or leaving it undocumented (it is then lost). The `scrum_master` agent owns issue and milestone lifecycle; you record the find.

- `github_id` is a stable identifier (the issue number, or a slug like `bug-totp-replay`). Stability matters because `log_issue` upserts on it: a re-run updates rather than duplicates.
- `type_` is the class (`bug`, `defect`, `tech-debt`, `regression`); `status` is `open` when you file it, `closed` when it is resolved and verified.
- Call `get_open_issues()` before starting a task and before filing, so you do not re-file a known defect and so you pick up context the previous agent left.
- If the defect blocks your current change, file it, then either fix it under a covering test as part of this branch (and say so in the handoff) or stop and escalate. Never ship a fix for it with no test.

## save_session — checkpoint long tasks

`save_session(session_id, agent_name, task, messages)`. This is the resume point for work that spans many steps or risks context loss. It upserts on `session_id`, so pick a stable id (the branch name or the issue id) and write to it repeatedly.

- Checkpoint at real boundaries: after each green in a long TDD loop, before a context-heavy operation (large refactor, dependency bump), and before you end a work block.
- `messages` is the structured state, not a transcript. Record: what is done, what is next, the current red/green position, the files touched, and any decision/issue ids you created. The test for a good checkpoint: another engineer could resume from it without you.
- `task` is a one-line description so `get_latest_activity` and `get_session` surface a readable entry.
- Keep secrets, tokens, and credentials out of `messages`. The store is shared project memory; treat it as you would a code comment, never as a vault. The same rule binds `save_memory(key, value, category)`, which is for durable facts (an environment quirk, a chosen config key), not ephemeral state.

## log_handoff — closing out to QA

`log_handoff(sender, recipient, contract_type, contract_path, status)`. The handoff row is a pointer; the substance lives in the file at `contract_path`. Write that file first, then log the row.

- `sender="software_engineer"`, `recipient="qa"`, `contract_type="code"` (or `implementation`), `status="pending"` until QA accepts.
- `contract_path` points at a written verification contract (extend `PLAN.md` or a dedicated `handoff-<branch>.md`). It must contain: the behavior added or changed, the exact files touched, the tests that cover it and the command to run them, any edges left uncovered and why, setup/env needed to reproduce, and the acceptance criteria each change maps to. This is what the `qa` agent needs to verify without interrogating you.
- Log the handoff only after the `definition_of_done` for the change holds (every behavior had a red test first, now green; suite passes). A handoff of unfinished work wastes the QA cycle.
- Handoffs are append-only; do not re-log the same one on a retry. If the contract changed, write a new contract file and a new handoff that supersedes the old.

## Resuming from memory

Start a task by reading the record, not the code. `get_latest_activity()` returns the most recent session or handoff and is your entry point. From there: `get_session(session_id)` to restore a checkpoint, `get_open_issues()` to pick up known defects, and `get_decision(decision_id)` to recover the rationale behind code you are about to change so you do not unknowingly reverse a deliberate choice. If a decision blocks what you intend, supersede it with a new `save_decision` that references the old one rather than silently overriding it.

## Common pitfalls

- A `save_decision` with no rejected alternatives in `rationale`. It records what, not why, and is useless to the next agent. Reject it.
- Logging trivial choices, flooding the decision log so the real tradeoffs are buried. Decisions are for the non-obvious few.
- Unstable `session_id` or `github_id`, so retries create duplicate rows instead of upserting. Derive them from the branch or issue.
- A `log_handoff` whose `contract_path` points at a missing or empty file, or a file with no "how to verify" steps. The pointer is worthless without the contract.
- Handing off before `definition_of_done` holds (tests not green, suite not run). QA bounces it and the loop is wasted.
- Silently fixing an out-of-scope defect with no `log_issue` and no covering test, or filing it and then patching it on the same branch without saying so in the handoff.
- Secrets, tokens, or credentials written into `messages`, a decision `rationale`, or a `save_memory` value. The store is shared and not a secrets manager.
- Treating a write failure as fatal and aborting the task, or assuming it succeeded without checking. Log the warning, verify the read, continue.
- Resuming by re-reading the diff instead of `get_latest_activity`/`get_session`, so prior context and decisions are lost.

## Definition of done

- [ ] Every non-obvious design choice is in `save_decision` with context, rejected alternatives, outcome, author, current branch, and (post-commit) `commit_sha`.
- [ ] Out-of-scope defects discovered during the work are in `log_issue` with a stable `github_id`, correct `type_`, and `status=open`; `get_open_issues()` was checked first.
- [ ] Long tasks have a `save_session` checkpoint with a stable id, written as resumable state (done / next / red-green / files / linked ids), not a transcript.
- [ ] A `log_handoff` to `qa` exists with `status=pending` and a `contract_path` to a file listing what changed, the covering tests and their run command, uncovered edges, setup, and acceptance-criteria mapping.
- [ ] The handoff was logged only after the change's `definition_of_done` held and the suite ran green.
- [ ] No secrets, tokens, or credentials appear in any memory value, session message, or decision rationale.
- [ ] The task began with `get_latest_activity` and the relevant `get_session`/`get_open_issues`/`get_decision` reads, so prior context was honored rather than re-derived.
