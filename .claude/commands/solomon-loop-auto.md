---
description: Fully autonomous parallel loop - spawn multiple agents to start, develop, test, review and open PRs for ready issues
argument-hint: (optional) --issues 42,43
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, AskUserQuestion
---

You are running the fully autonomous parallel loop stage.

## 1. Ask for Concurrency Limit

Ask the user using the AskUserQuestion tool (or standard chat response if the tool is not available):
"How many concurrent agents (concurrency limit) do you want to run in parallel? (Default: 3)"

## 2. Execute the Loop

Once you have the limit (default to 3 if not specified), run the parallel loop orchestrator via the Bash tool:
```bash
uv run python -m solomon_harness.cli dev loop-auto --concurrency <limit> $ARGUMENTS
```

After the command completes, summarize the success/failure of each issue's autonomous pipeline.
