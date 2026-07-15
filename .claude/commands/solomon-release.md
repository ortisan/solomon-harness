---
description: Cut a release for a completed milestone (or an on-demand patch batch): run the library readiness gate, then open the chore/release prep PR for the human to merge (sre).
argument-hint: [milestone]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Bash(scripts/wiki-sync.sh:*), Task, Read, Write, Edit, AskUserQuestion, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__save_release, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__link_session_handoff, mcp__solomon-memory__get_latest_activity
---

Read and follow `solomon_harness/catalog/workflows/solomon-release.md`.
Treat `$ARGUMENTS` as the value of `{{arguments}}` in that workflow.
