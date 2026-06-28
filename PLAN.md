# PLAN — Issue #29: hermeticity regression guard (guard-only)

Slice A/3 of bug #24. Branch `bugfix/hermetic-test-backend` (worktree `../sh-29`, base `main` at v0.2.0).

## Problem statement

Verified during start: the suite is already hermetic — no real memory-DB write, no real headless/subprocess spawn (see the #29 scope correction). The gap is that nothing *enforces* it: a future change could silently introduce a real shared-SurrealDB write or a real engine spawn and still pass. This slice adds a minimal red-before-green guard that fails loudly if either invariant is broken. Per the chosen scope, this is **guard only** — the cosmetic "Indexing…"/"Running … headless …" prints are left as-is.

## Proposed change and the boundary it touches

Test-only. Add one new test module. No production code change (the fail-closed behavior and the mockable subprocess seam already exist in `database_client.py` and `workflows.py`); the guard pins them against regression.

## Target files (fence)

- `tests/test_hermeticity.py` (new) — the only file changed.

## Guard design (the two enforced invariants)

1. **DB fails closed to SQLite when the real shared backend is unreachable.** Construct a `DatabaseClient` against the real repo config (surreal provider) with `SURREAL_URL` set to an unreachable sentinel (`ws://127.0.0.1:1/rpc`) and `SURREAL_USER`/`SURREAL_PASS` cleared; assert `backend == "sqlite"` and that no exception escapes. This proves a test can never silently connect to or write the real shared multi-tenant SurrealDB — it always falls back. A regression that made the client hard-depend on the real backend would trip this.
2. **The headless engine is reachable only through the mockable `subprocess.run` seam.** Patch `subprocess.run` with a sentinel; call `workflows.run_stage(root, "start", ["42"], engine="claude")`; assert the sentinel was invoked (so the spawn is fully interceptable) and that no real process ran. A regression adding a non-mockable real-exec path (e.g. `os.system`, a direct `Popen`) would not route through the patch and would trip this.

## Red-before-green

The guard passes on today's (already hermetic) code, so "red" is shown by a temporary injected violation during development: (a) point the DB guard at a reachable real backend with creds to confirm it would otherwise resolve to `surrealdb`, and (b) replace the engine call with a direct unpatched exec to confirm the seam guard trips. Both throwaway checks are reverted before commit; the committed guard is green against real code. This is documented in the PR so the guard's failure mode is demonstrated, not assumed.

## Edge cases (observable)

- A future test that spawns a real `claude`/`gemini` process via a non-mockable path → invariant 2 fails, naming the call.
- A future `DatabaseClient` change that connects to the real shared SurrealDB instead of failing closed → invariant 1 fails.

## STRIDE notes

Test-only; no production surface changes. The guard reduces a real data-integrity/isolation risk: a regression silently writing the shared multi-tenant SurrealDB (cross-tenant Tampering) or spawning an unintended process (untrusted Execution). No secrets or untrusted input introduced.

## Verification criteria

- `uv run python -m unittest tests.test_hermeticity` passes (both invariants green).
- The guard demonstrably fails when each invariant is violated (shown once during development, reverted).
- No production files changed; the rest of the suite is unaffected (`uv run python -m unittest discover -s tests` unchanged except the new module).

## Note

The worktree-parity failures (`test_home`, `test_bootstrap` kanban) and the missing `pytest` dev extra are out of scope here — they are #30 and #31.
