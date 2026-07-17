---
description: Headless batch loop - run N sequential workflow iterations over ready issues, human-gated at merge
argument-hint: (optional) --issues 42,43
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, AskUserQuestion, mcp__solomon-memory__get_memory
---

You are running the headless batch loop stage: N sequential workflow iterations, each a fresh engine subprocess under the single-driver lock, always human-gated at merge.

## 1. Ask for the Iteration Count

Ask the user using the AskUserQuestion tool (or standard chat response if the tool is not available):
"How many sequential workflow iterations do you want to run? (Default: 3)"

## 2. Execute the Loop

Once you have the count (default to 3 if not specified), run the batch loop runner via the Bash tool (the `--concurrency` flag name is historical — iterations run sequentially under one lock):
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
