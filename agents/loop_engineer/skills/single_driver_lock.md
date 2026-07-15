---
name: single-driver-lock
description: Governs the single-driver lock protocol in solomon_harness/loop_lock.py, including atomic acquisition, git-common-dir anchoring, stale and pid-reuse reclaim rules, and recovery via loop-lock status and release. Use when debugging a blocked headless stage, a stuck lock, or the loop-guard hook blocking a driver's own push.
---

# Single-Driver Lock

Every HEADLESS driver (the `solomon-harness dev` cadence path) acquires the single-driver lock before a mutating stage touches git or the board; this skill governs the lock protocol and its recovery, the precondition that makes a cadence safe. Two concurrent drivers once produced premature merges that bypassed the review gate and flipped `core.bare=true`; the lock makes that race impossible-by-construction on the headless path. Interactive `/solomon-*` sessions do not acquire the lock — they are bounded by the human merge gate and the `loop-guard` hook, and operators run one at a time; do not claim the lock protects concurrent interactive drivers.

## The protocol (`solomon_harness/loop_lock.py`)

- **Anchor at the git common dir.** `resolve_lock_path` resolves `.git` directly (dir or linked-worktree file, without shelling out to git) and places the lock at `<common>/solomon-loop.lock`, so every linked worktree contends on one file. A per-checkout lock gives zero cross-worktree exclusion and must never be used. The fallback for a non-git dir is `<root>/.agents/solomon/state/loop.lock`.
- **Atomic acquire.** `LoopLock.acquire()` creates the file with `os.O_CREAT | os.O_EXCL`. If it exists: a same-session lock is re-entrant (heartbeat refreshed); a live foreign lock raises `LoopLockHeld`; a stale lock is reclaimed by atomic `os.replace`, then re-read to confirm the win — when two drivers race to reclaim the same dead lock, the last writer wins and the loser sees a live foreign holder on re-read and backs off (`test_reclaim_cas_loser_backs_off`).
- **Staleness favors safety.** A live process on the SAME host is never stale, however long it has held the lock and even though the heartbeat is never refreshed mid-run — a long stage must not have its lock stolen. Only a dead same-host pid, or a cross-host lock whose heartbeat is older than the TTL (`DEFAULT_TTL_SECONDS = 1800`; a remote pid cannot be probed), is reclaimable.
- **Pid reuse is detected.** A live pid alone is not proof the holder still runs: after a crash the OS may hand the pid to an unrelated process, and `os.kill(pid, 0)` would report that impostor alive forever. The lock body therefore records `pid_started_at` (read via `ps -o lstart=`, which works on Linux and macOS with no extra dependency), and `is_stale` compares it against the current start time of whatever now answers to that pid; a mismatch means the pid was recycled and the lock is reclaimable. A lock written without the field, or a failed lookup, degrades to liveness-only.
- **Auditable private body.** The lock is mode `0600` JSON — `session_id`, `pid`, `pid_started_at`, `host`, `stage`, `acquired_at`, `heartbeat_at`, plus an optional `shell_capability` record. That record contains only the bearer-token digest, owning session, exact operation scopes, and allowed non-protected branch patterns.

## Enforcement and recovery

- **Portable gate.** `run_stage` (`solomon_harness/workflows.py`) acquires the lock for every headless stage; idea/issue/bug/refine mutate GitHub or the board even when they do not touch a branch. It refuses with exit code 1 when a foreign live lock is held. This Python gate is shared by Claude, AGY, and Codex. The lock is released in a `finally` block, after the `loop_runs` entry is written with `lock.session_id`, so a failed engine still leaves an auditable trail and a normal exit never leaks the lock.
- **Native pre-tool guards.** The compiler registers the same `solomon-harness host-hook pre-tool-use` policy in `.claude/settings.json`, `.agents/hooks.json`, and inline in `.codex/config.toml`. Every normalized shell segment is an explicit read-only form, a known mutator with statically proven targets, a permanently denied dangerous form, or a `dev:execute` request. An opaque executable or interpreter is denied without a matching live capability; with that capability it may run so arbitrary repositories can use their real build, test, framework, and container CLIs. Known filesystem mutators and dangerous Git/merge/config/code-exec options stay under their stricter parsers and cannot use this fallback. The capability is an authorization boundary, not a syscall sandbox: authorized child code can write through syscalls, so autonomous stages still require a trusted checkout and least-privilege OS/container context. Each adapter serializes the same verdict in its native protocol.
- **Autonomy scope.** Human and L2/L3 delivery stages receive the documented development, GitHub-mutation, and non-protected Git scopes. L1 `workflow` receives only `harness:read`; its token cannot authorize `dev:execute`, `gh:mutate`, commit, push, or worktree creation.
- **Scoped capability.** Trusted `run_stage` creates an ephemeral token after acquiring the lock and passes it only to its engine child. Git add/branch/checkout/commit/fetch/push/switch/worktree forms require the matching token, session, live lock, operation scope, and feature/fix/chore/docs/refactor/test branch scope. Push must name one remote and one explicit branch. Main/master/trunk/develop/release branches, force/delete/bulk pushes, tag/pull/rebase/reset/restore/clean/apply/rm/mv, and direct Git/GitHub merge forms are denied autonomously. A nested same-session stage reuses the still-valid token.
- **Recovery.** `solomon-harness loop-lock status` prints the lock path, the holder's session/pid/host, the stage, both timestamps, and `live` versus `STALE (reclaimable)`. `solomon-harness loop-lock release` force-removes the file and warns first when a live foreign driver still owns it — run it only after `status` shows STALE or you have confirmed the holder process is gone; a stale lock is also reclaimed automatically by the next `acquire()`.

## Session identity and the own-worker false positive

`session_id` resolves from `SOLOMON_SESSION_ID`, then `CLAUDE_SESSION_ID`, else `host:pid`. A headless `run_stage` child receives `SOLOMON_SUBPROCESS=1`, the outer driver's `SOLOMON_SESSION_ID`, and its ephemeral shell capability. Identity alone is insufficient for a Git mutation. Outside that lineage, the hook uses the native payload identity. Missing inherited identity fails closed. Parsing covers option-bearing forms such as `git -C <dir> commit`, `git -c key=value push`, and `gh --repo owner/repo pr merge`; repository-path overrides are denied.

## Concurrency truth comes from the lockfile, not a row count

The "is another driver running" signal must derive from the lockfile, never from a database row count: under the SQLite fallback each worktree has its own database, so a cross-worktree count is invisible. The lock is the single shared truth.

## Common pitfalls

- Placing the lock per-worktree instead of at the git common dir — no cross-worktree exclusion.
- Deriving a concurrent-driver warning from `loop_runs` rows — invisible under the SQLite fallback.
- A memory-backed lease instead of a filesystem lock — TOCTOU window plus SQLite-fallback divergence.
- Holding the lock across an interactive session it can outlive — keep acquisition inside `run_stage` for the stage's duration.
- Releasing a live lock because the hook blocked a worker's own push — verify the holder with `loop-lock status` first; a false positive on your own lineage is not a stale lock.
- Treating an empty target list as proof a command is safe — unknown and opaque executables must fail closed.
- Persisting or placing the raw capability on a command line — only its digest belongs in the private lock record.
- Trusting `os.kill(pid, 0)` alone for staleness — pid reuse makes a dead holder look alive forever; the `pid_started_at` comparison exists for exactly that gap.

## Definition of done

- [ ] The lock anchors at `git rev-parse --git-common-dir` (resolved without shelling out to git).
- [ ] Acquire is atomic (`O_EXCL`); stale, dead-pid, and recycled-pid locks are reclaimable; same-session is re-entrant; a lost reclaim race backs off.
- [ ] Mutating stages refuse to run (exit 1) while a foreign live lock is held on Claude, AGY, and Codex.
- [ ] Shell classification, capability scope/session/branch checks, and permanent merge/protected-branch denials have parity on Claude, AGY, and Codex.
- [ ] Recovery (`loop-lock status` / `release`) is available and documented, including the own-worker false positive.
- [ ] Any change ships with covering tests in `tests/test_loop_lock.py`.
