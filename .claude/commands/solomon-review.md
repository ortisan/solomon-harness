---
description: Review a pull request through QA, security, and architecture gates, then approve or request changes
argument-hint: [pr-number]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Write, AskUserQuestion, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_issue, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__link_session_handoff, mcp__solomon-memory__get_open_issues, mcp__solomon-memory__get_latest_activity
---

Read and follow `solomon_harness/catalog/workflows/solomon-review.md`.
Treat `$ARGUMENTS` as the value of `{{arguments}}` in that workflow.
