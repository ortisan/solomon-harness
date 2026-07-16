---
description: Standing reconciliation — converge closed issues in memory and on the canonical board
argument-hint: (optional) --dry-run
allowed-tools: Bash(uv run:*)
---

You are running the standing reconciliation stage. Execute exactly:

```bash
uv run python -m solomon_harness.cli reconcile $ARGUMENTS
```

The CLI acquires the repository-wide single-driver lock and only projects a
terminal board status when GitHub already reports CLOSED. It is idempotent: a
canonical card already in `Done` receives no write.

Never merge or close a pull request or issue, never release, and never move an
open issue to `Done`. Report the command's summary or failure and stop.
