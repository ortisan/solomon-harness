# Single-Driver Lock

Every HEADLESS driver (the `solomon-harness dev` cadence path) acquires the single-driver lock before a mutating stage touches git or the board; this skill governs the lock protocol and its recovery, the precondition that makes a cadence safe. Two concurrent drivers once produced premature merges that bypassed the review gate and flipped `core.bare=true`; the lock makes that race impossible-by-construction on the headless path. Interactive `/solomon-*` sessions do not acquire the lock — they are bounded by the human merge gate and the `loop-guard` hook, and operators run one at a time; do not claim the lock protects concurrent interactive drivers.

## The protocol (`solomon_harness/loop_lock.py`)

- **Anchor at the git common dir.** `resolve_lock_path` resolves `.git` directly (dir or linked-worktree file, without shelling out to git) and places the lock at `<common>/solomon-loop.lock`, so every linked worktree contends on ONE file. A per-checkout `.solomon/loop.lock` gives zero cross-worktree exclusion and must never be used — it fails the exact incident it targets. The fallback for a non-git dir is `<root>/.solomon/loop.lock`.
- **Atomic acquire.** `LoopLock.acquire()` creates the file with `os.O_CREAT | os.O_EXCL`. If it exists: a same-session lock is re-entrant (heartbeat refreshed); a live foreign lock raises `LoopLockHeld`; a stale lock is reclaimed by atomic `os.replace`, then re-read to confirm the win — when two drivers race to reclaim the same dead lock, the last writer wins and the loser sees a live foreign holder on re-read and backs off (`test_reclaim_cas_loser_backs_off`).
- **Staleness favors safety.** A live process on the SAME host is never stale, however long it has held the lock and even though the heartbeat is never refreshed mid-run — a long stage must not have its lock stolen. Only a dead same-host pid, or a cross-host lock whose heartbeat is older than the TTL (`DEFAULT_TTL_SECONDS = 1800`; a remote pid cannot be probed), is reclaimable.
- **Pid reuse is detected.** A live pid alone is not proof the holder still runs: after a crash the OS may hand the pid to an unrelated process, and `os.kill(pid, 0)` would report that impostor alive forever. The lock body therefore records `pid_started_at` (read via `ps -o lstart=`, which works on Linux and macOS with no extra dependency), and `is_stale` compares it against the current start time of whatever now answers to that pid; a mismatch means the pid was recycled and the lock is reclaimable. A lock written without the field, or a failed lookup, degrades to liveness-only.
- **Auditable body.** The lock is plain JSON — `session_id`, `pid`, `pid_started_at`, `host`, `stage`, `acquired_at`, `heartbeat_at` — so the holder is itself a file on disk.

## Enforcement and recovery

- **Portable gate.** `run_stage` (`solomon_harness/workflows.py`) acquires the lock for `LOCKED_STAGES` (`loop`, `loop-auto`, `start`, `review`, `release`, `scan-arch`, `scan-dedup`), plus any stage `requires_lock` names at autonomy L3, and refuses with exit code 1 when a foreign live lock is held. This is Python the runner calls, so it holds on both Claude Code and the Gemini CLI — not only in a Claude-only hook. The lock is released in a `finally` block, after the `loop_runs` entry is written with `lock.session_id`, so a failed engine still leaves an auditable trail and a normal exit never leaks the lock.
- **PreToolUse guard (Claude only).** The `loop-guard` hook (`.claude/settings.json`, matcher `Bash|Edit|Write|MultiEdit|NotebookEdit`, command `uv run python -m solomon_harness.cli loop-guard`) blocks `git push` / `gh pr merge` / `git merge` while a foreign live lock is held: exit 2 blocks and feeds the reason back to the model; any internal error exits 0. It is defense-in-depth and fails open — the portable `run_stage` gate is the enforcement of record.
- **Recovery.** `solomon-harness loop-lock status` prints the lock path, the holder's session/pid/host, the stage, both timestamps, and `live` versus `STALE (reclaimable)`. `solomon-harness loop-lock release` force-removes the file and warns first when a live foreign driver still owns it — run it only after `status` shows STALE or you have confirmed the holder process is gone; a stale lock is also reclaimed automatically by the next `acquire()`.

## Session identity and the own-worker false positive

`session_id` resolves from `SOLOMON_SESSION_ID`, then `CLAUDE_SESSION_ID`, else `host:pid`. The hook builds its `LoopLock` from the hook payload's `session_id`, and that id is not the driver's: an engine session spawned under a lock-holding `dev` driver carries its own fresh session id, so `guard_verdict` sees the driver's lock as foreign and can block the worker's OWN push. Recovery: run `solomon-harness loop-lock status`, confirm the holder's host and pid belong to your own driver lineage, and do not release the lock. Note the guard regex matches only the adjacent forms `git push`, `gh pr merge`, `git merge` — `git -C <dir> push` is not intercepted — so its coverage is narrower than "all pushes"; one more reason the portable gate, not the hook, is the safety boundary.

## Concurrency truth comes from the lockfile, not a row count

The "is another driver running" signal must derive from the lockfile, never from a database row count: under the SQLite fallback each worktree has its own database, so a cross-worktree count is invisible. The lock is the single shared truth.

## Common pitfalls

- Placing the lock per-worktree instead of at the git common dir — no cross-worktree exclusion.
- Deriving a concurrent-driver warning from `loop_runs` rows — invisible under the SQLite fallback.
- A memory-backed lease instead of a filesystem lock — TOCTOU window plus SQLite-fallback divergence.
- Holding the lock across an interactive session it can outlive — keep acquisition inside `run_stage` for the stage's duration.
- Releasing a live lock because the hook blocked a worker's own push — verify the holder with `loop-lock status` first; a false positive on your own lineage is not a stale lock.
- Trusting `os.kill(pid, 0)` alone for staleness — pid reuse makes a dead holder look alive forever; the `pid_started_at` comparison exists for exactly that gap.

## Definition of done

- [ ] The lock anchors at `git rev-parse --git-common-dir` (resolved without shelling out to git).
- [ ] Acquire is atomic (`O_EXCL`); stale, dead-pid, and recycled-pid locks are reclaimable; same-session is re-entrant; a lost reclaim race backs off.
- [ ] Mutating stages refuse to run (exit 1) while a foreign live lock is held, on both hosts.
- [ ] Recovery (`loop-lock status` / `release`) is available and documented, including the own-worker false positive.
- [ ] Any change ships with covering tests in `tests/test_loop_lock.py`.
