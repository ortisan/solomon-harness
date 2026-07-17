---
name: solomon-reconcile
description: "Standing reconciliation — converge closed issues in memory and on the canonical board Use when the user asks to run the corresponding Solomon stage or explicitly invokes $solomon-reconcile."
---

# solomon-reconcile

Apply this workflow when the user invokes the skill or asks for the stage it governs. Treat `ARGUMENTS` in the workflow below as the arguments supplied with the skill invocation or elsewhere in the conversation.

Codex compatibility rules:

- References to `/solomon-*` identify Solomon workflow stages. In Codex, invoke a stage explicitly with its `$solomon-*` skill name.
- When the workflow names Claude-specific Task or AskUserQuestion tools, use the equivalent sub-agent delegation or structured user-input capability available in the current Codex session.
- Read specialist definitions and skills under `agents/<name>/` before acting in that role.

You are running the standing reconciliation stage. Execute exactly:

```bash
uv run python -m solomon_harness.cli reconcile ARGUMENTS
```

The CLI acquires the repository-wide single-driver lock and only projects a
terminal board status when GitHub already reports CLOSED. It is idempotent: a
canonical card already in `Done` receives no write.

Never merge or close a pull request or issue, never release, and never move an
open issue to `Done`. Report the command's summary or failure and stop.
