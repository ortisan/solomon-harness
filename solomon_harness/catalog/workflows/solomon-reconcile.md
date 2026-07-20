---
description: Standing reconciliation — converge memory and the canonical board with GitHub: close delivered rows, import missing open issues
argument-hint: (optional) --dry-run
---

You are running the standing reconciliation stage. Execute exactly:

```bash
uv run python -I -m solomon_harness.cli reconcile {{arguments}}
```

The CLI acquires the repository-wide single-driver lock and only projects a
terminal board status when GitHub already reports CLOSED. It also imports a
memory row for each GitHub-OPEN issue the memory has never seen -- a
memory-only write with a non-terminal status, never a board move. It is
idempotent: a canonical card already in `Done` receives no write, and an
already-tracked issue is never re-imported.

Never merge or close a pull request or issue, never release, and never move an
open issue to `Done`. Report the command's summary or failure and stop.
