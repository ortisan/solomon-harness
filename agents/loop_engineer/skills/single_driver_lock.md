# Single-Driver Lock

Every driver acquires the single-driver lock before it touches git or the board; this skill governs the lock protocol and its recovery, the precondition that makes any cadence safe. Two concurrent drivers once produced premature merges that bypassed the review gate and flipped `core.bare=true`; the lock converts that race into impossible-by-construction.

## The protocol (`solomon_harness/loop_lock.py`)

- **Anchor at the git common dir.** `resolve_lock_path` resolves `.git` directly (dir or worktree file) and places the lock at `<common>/solomon-loop.lock`, so every linked worktree contends on ONE file. A per-checkout `.solomon/loop.lock` gives zero cross-worktree exclusion and must never be used — it fails the exact incident it targets. The fallback for a non-git dir is `<root>/.solomon/loop.lock`.
- **Atomic acquire.** `LoopLock.acquire()` creates the file with `os.O_CREAT | os.O_EXCL`. If it exists: a same-session lock is re-entrant (heartbeat refreshed); a live foreign lock raises `LoopLockHeld`; a stale lock is reclaimed.
- **Staleness favors safety.** A live process on the SAME host is never stale, however long it has held the lock and even though the heartbeat is never refreshed mid-run — a long stage must not have its lock stolen. Only a dead same-host pid, or a cross-host lock whose heartbeat is older than the TTL (`DEFAULT_TTL_SECONDS = 1800`; a remote pid cannot be probed), is reclaimable. The body is plain JSON (`session_id`, `pid`, `host`, `stage`, `acquired_at`, `heartbeat_at`), so the holder is itself auditable.

## Enforcement and recovery

- **Portable gate.** `run_stage` acquires the lock for `LOCKED_STAGES` (`loop`, `start`, `review`, `release`, `scan-arch`, `scan-dedup`) and refuses (`return 1`) when a foreign live lock is held. This is Python the runner calls, so it holds on both Claude Code and the Gemini CLI — not only in a Claude-only hook.
- **PreToolUse guard (Claude only).** The `loop-guard` hook blocks `git push` / `gh pr merge` while a foreign lock is held; it is defense-in-depth and fails open. The portable `run_stage` gate is the enforcement of record.
- **Recovery.** `solomon-harness loop-lock status` shows the holder and staleness; `solomon-harness loop-lock release` clears a stuck lock after a crash.

## Concurrency truth comes from the lockfile, not a row count

The "is another driver running" signal must derive from the lockfile, never from a database row count: under the SQLite fallback each worktree has its own database, so a cross-worktree count is invisible. The lock is the single shared truth.

## Common pitfalls

- Placing the lock per-worktree instead of at the git common dir — no cross-worktree exclusion.
- Deriving a concurrent-driver warning from `loop_runs` rows — invisible under the SQLite fallback.
- A memory-backed lease instead of a filesystem lock — TOCTOU window plus SQLite-fallback divergence.
- Holding the lock across an interactive session it can outlive — keep acquisition inside `run_stage` for the stage's duration.

## Definition of done

- [ ] The lock anchors at `git rev-parse --git-common-dir` (resolved without shelling out to git).
- [ ] Acquire is atomic (`O_EXCL`); stale/dead-pid locks are reclaimable; same-session is re-entrant.
- [ ] Mutating stages refuse to run while a foreign live lock is held, on both hosts.
- [ ] Recovery (`loop-lock status` / `release`) is available and documented.
- [ ] Any change ships with covering tests in `tests/test_loop_lock.py`.
