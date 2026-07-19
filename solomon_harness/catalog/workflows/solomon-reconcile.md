---
description: Standing reconciliation — converge closed issues in memory and on the canonical board
argument-hint: (optional) --dry-run
---

You are running the standing reconciliation stage. Execute exactly:

```bash
uv run python -I -m solomon_harness.cli reconcile {{arguments}}
```

The CLI acquires the repository-wide single-driver lock and only projects a
terminal board status when GitHub already reports CLOSED. It is idempotent: a
canonical card already in `Done` receives no write.

Never merge or close a pull request or issue, never release, and never move an
open issue to `Done`. Report the command's summary or failure and stop.
