---
description: Standing maintenance loop — scan the codebase for one architectural drift and open a single draft PR
argument-hint: (optional) a path or subsystem to focus the scan
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Grep, Glob, AskUserQuestion, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_issue
---

Read and follow `solomon_harness/catalog/workflows/solomon-scan-arch.md`.
Treat `$ARGUMENTS` as the value of `{{arguments}}` in that workflow.
