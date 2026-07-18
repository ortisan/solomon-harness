---
description: Headless batch loop - run N sequential workflow iterations over ready issues, human-gated at merge
argument-hint: (optional) --issues 42,43
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, AskUserQuestion, mcp__solomon-memory__get_memory
---

Read and follow `solomon_harness/catalog/workflows/solomon-loop.md`.
Treat `$ARGUMENTS` as the value of `{{arguments}}` in that workflow.
