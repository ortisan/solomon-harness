# ADR-0022: Same-session lock reentrance for nested headless dev stage calls

- Status: accepted
- Date: 2026-07-04
- Deciders: loop_engineer
- Issue: #197

## Context and problem statement

Live-reproduced on 2026-07-04, one layer below the bug ADR-0021 fixed. Once a
headless `solomon-harness dev loop --concurrency N` iteration correctly enters
Autonomous Mode, it determines the next step is itself a `LOCKED_STAGES` member
(e.g. `solomon-harness dev review 195`) and shells that out from inside the
`claude -p` session `dev loop` is driving. That nested call was refused:
`Error: another solomon driver holds the loop lock (...)`, with the reported
holder being the PARENT `dev loop` process itself, synchronously blocked inside
its own `subprocess.run` waiting on this very child.

The confirmed process-boundary shape, read precisely from
`solomon_harness/workflows.py` (`run_stage`) and `solomon_harness/loop_lock.py`:

- `run_stage` acquires `LoopLock(workspace_root, stage="loop")` and holds it for
  the whole run. `LoopLock.__init__` resolves `session_id` as `session_id or
  os.environ.get("SOLOMON_SESSION_ID", os.environ.get("CLAUDE_SESSION_ID",
  f"{host}:{pid}"))` — with neither env var set, it falls back to
  `f"{host}:{parent_pid}"` (`solomon_harness/loop_lock.py:180-182`).
- It then calls `subprocess.run([engine, "-p"], ..., env=clean_git_env())`
  (`solomon_harness/workflows.py:304-318`, pre-fix). `clean_git_env()` only
  strips `GIT_*` keys from a copy of `os.environ`
  (`solomon_harness/subprocess_env.py:21-23`) — since `SOLOMON_SESSION_ID` was
  never an actual exported env var (the fallback identity lived only on the
  Python `LoopLock` instance), the child's environment carries no session
  identity at all.
- `claude -p` is a real, separate OS process (child). Its Bash tool spawns
  `solomon-harness dev review 195` as a further real OS process (grandchild),
  inheriting the child's environment. This is a true three-level nested OS
  subprocess chain (parent `dev loop` -> `claude -p` child -> `dev review`
  grandchild) — not merely a same-process tool call.
- The grandchild's own `run_stage` constructs a brand-new `LoopLock`. With no
  `SOLOMON_SESSION_ID` in its inherited environment, it falls back to
  `f"{host}:{grandchild_pid}"` — a different string than the parent's
  `f"{host}:{parent_pid}"`, purely because the two processes have different
  pids. `LoopLock.acquire()` finds the lock file, sees a session_id mismatch,
  checks `is_stale` (false: the parent pid is alive on the same host — it is
  blocked in `subprocess.run`, not dead), and raises `LoopLockHeld`.

This is the confirmed shape: a real nested-OS-subprocess chain (candidate (a)
in the issue), whose specific broken link is exactly candidate (b)'s
description — `clean_git_env()` passes through only what already exists in
`os.environ`; it never exports the resolved `session_id` for a nested process
to inherit. `LoopLock.acquire()` already contains a same-session reentrant
branch (`solomon_harness/loop_lock.py`, the `FileExistsError` handler: `if
info.get("session_id") == self.session_id: refresh and return`) — it is simply
unreachable from the nested call today because the identity never arrives.

A second, related gap surfaced while designing the fix: if the reentrant
branch is reached and later this SAME nested `LoopLock` calls `release()` in
its own `finally` (as `run_stage` always does), the pre-existing `release()`
unconditionally removes the file whenever `session_id` matches — which it now
does, because the nested call resolved the identical session_id. That deletes
the shared lock while the outer `dev loop` process is still mid-run, reopening
a window for a genuinely different, third driver to acquire the now-absent
lock — the exact concurrent-driver race this lock exists to close (see the
"Concurrent loop drivers race" incident history: premature merges bypassing
the review gate, worktree tooling flipping `core.bare=true`). A reentrant
holder must not own the lock's release lifecycle.

## Decision drivers

- The single-driver guarantee is the safety floor the whole loop-engineering
  roadmap depends on (ADR-0010): a genuinely different driver must still be
  refused. This fix closes only the same-driver, nested-call gap.
- Minimal blast radius: the fix must not touch the Claude Code PreToolUse
  `loop-guard` hook (a different, host-specific enforcement layer this repo's
  Python code does not own) or `loop_policy.py`'s autonomy ladder / human-gated
  stages.
- Correctness under nesting depth: a reentrant acquire must not silently
  become the party responsible for tearing the lock down; only the call that
  actually created or reclaimed it owns that.

## Considered options

- Inject `SOLOMON_SESSION_ID=lock.session_id` into the engine child's
  environment at the `run_stage` dispatch site, and rely entirely on the
  existing reentrant branch in `LoopLock.acquire()`. Rejected alone: it closes
  the acquire-side gap but leaves the release-side gap open (a nested reentrant
  release frees the lock early).
- The above, plus track reentrance on the `LoopLock` instance and make
  `release()` a no-op for a reentrant holder. Chosen: closes both the acquire
  gap (the actual reported bug) and the release gap it exposes, with a small,
  local change confined to `loop_lock.py` and `workflows.py`.
- Depth-count the lock in the file itself (e.g. a `holders: N` field,
  incremented/decremented per acquire/release). Rejected: adds persistent
  shared mutable state and a new failure mode (a crashed nested holder leaves
  the count wrong forever); the in-memory reentrant flag needs no such
  cross-process bookkeeping because only the object that actually created the
  file needs to know it owns the release.
- Have the nested `dev <stage>` call skip lock acquisition entirely when it
  detects it is loop-driven (e.g. an env flag meaning "don't lock, my parent
  already does"). Rejected: this stops treating the nested call as a first-
  class, independently auditable stage run and would need its own new signal;
  the existing reentrant-acquire branch already does this correctly once
  identity is reachable, at no cost to auditability (the lock file's `stage`
  field is refreshed to the nested stage on each reentrant heartbeat).

## Decision outcome

Chosen option: propagate the driver's own `session_id` into the engine child's
environment, and make a reentrant acquire release-safe.

- `solomon_harness/workflows.py`, `run_stage`: build `child_env =
  clean_git_env()` once; when a lock was acquired for this stage
  (`lock is not None`), set `child_env["SOLOMON_SESSION_ID"] = lock.session_id`
  before either `subprocess.run` call site (the cost-capturing L2/L3 path and
  the plain path). Any nested `solomon-harness dev <stage>` invocation shelled
  out from within that engine session inherits this var through normal OS
  environment inheritance and resolves the identical `session_id` in its own
  `LoopLock.__init__`.
- `solomon_harness/loop_lock.py`, `LoopLock`: add `self._reentrant: bool`,
  reset to `False` at the top of every `acquire()` call. The existing
  same-session branch in the `FileExistsError` handler now also sets
  `self._reentrant = True` before refreshing the heartbeat and returning. Every
  other acquisition path (fresh create, stale reclaim) leaves it `False`.
  `release()` returns immediately, without touching the file, when
  `self._reentrant` is `True`; otherwise its existing session-match-or-stale
  removal logic is unchanged.
- The genuine cross-session guard is untouched: a mismatched `session_id`
  still falls through to the existing `is_stale` check and `LoopLockHeld` when
  live, exactly as before. Only the identical-session path changes behavior,
  and only in the direction of reentrance already implied by the pre-existing
  branch.

### Consequences

- Positive: a headless `dev loop` iteration whose Autonomous Mode next step is
  a `LOCKED_STAGES` member now proceeds instead of failing at the first nested
  `dev <stage>` call — the failure mode reported in #197 and the regression
  test added for it. The outer driver's lock is never pulled out from under it
  by a nested call finishing first, closing a latent race the acquire-only fix
  would have introduced. A genuinely different session is still refused with
  no change in behavior.
- Negative: `LoopLock` now carries one bit of instance state whose only
  purpose is to make `release()` conditionally skip; a caller that constructs
  a `LoopLock`, never calls `acquire()`, and calls `release()` directly is
  unaffected (`_reentrant` defaults to `False`), but this is one more piece of
  state to keep in mind when reading the class.
- Scope: this fix changes only when a stage's engine subprocess reaches the
  dispatch call and whether a reentrant holder tears the lock down early. It
  does not touch `loop_policy.py`'s L1/L2/L3 ladder, `HUMAN_GATED_STAGES`, or
  the Claude Code `loop-guard` PreToolUse hook — merge, release, and Done stay
  permanently human-gated exactly as before.
- Follow-ups: none required by this fix.

## More information

- Implementation: branch `fix/loop-nested-session-lock-reentrance`;
  `solomon_harness/workflows.py` (`run_stage`), `solomon_harness/loop_lock.py`
  (`LoopLock.acquire`, `LoopLock.release`), covering tests in
  `tests/test_workflows.py` (`TestRunStageSessionIdPropagation`) and
  `tests/test_loop_lock.py`.
- Root-cause and reproduction: issue #197.
- Prior art this fix does not change: `docs/adr/0010-loop-single-driver-lock.md`
  (the single-driver lock itself), `docs/adr/0021-headless-loop-autonomous-mode-directive.md`
  (the layer above this one, fixed by #196).
- Related incident history: the "loop-guard blocks own worker push" issue is
  the same session-id-not-propagated-parent-to-child root cause, one layer up,
  inside the Claude Code PreToolUse hook rather than this repo's Python code;
  that hook is out of scope here.
- This decision is also recorded in the project memory via `save_decision`.
