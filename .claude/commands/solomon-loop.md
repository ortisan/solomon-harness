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
uv run python -m solomon_harness.cli dev loop --concurrency <limit> $ARGUMENTS
```

Capability gaps: the start/refine stages the loop drives run a Capability
Check (ADR-0008) and may report a capability gap in their output. The loop
only surfaces the gap — acquisition (adapt a skill, create an agent) is
human-gated, and `solomon-harness broker apply` refuses headless runs (exit 3).
Report any surfaced gap to the user as a candidate next action;
never attempt the acquisition from the loop.

Discovered problems: each agent follows the discovered-problem protocol (see
`docs/solomon-workflow.md`). A problem or better solution found while
implementing an issue becomes a NEW issue linked with `Refs #<parent>` — never
a comment appended to the in-flight issue, and never a silent widening of that
issue's diff. Surface the newly filed issues in the run summary.

After the command completes, summarize the success/failure of each issue's autonomous pipeline.
