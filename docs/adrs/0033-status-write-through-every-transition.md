# ADR-0033: Status write-through on every board transition, and a one-shot normalization pass

- Status: accepted
- Date: 2026-07-15
- Amends: ADR-0006 (decision points 1 and 2)
- Deciders: software_architect, software_engineer
- Issue: #173

## Context and problem statement

ADR-0006 deliberately gated the board-to-memory write-through on `status ==
"Done"` (decision point 2, option 2b) to bound the blast radius of a change to
a core write method, and it deliberately rejected a one-shot destructive
rewrite of stored status rows (decision point 1, option 1c) in favor of
normalize-on-write plus tolerant reads. Both were the right calls for the bug
they fixed (#101 — delivered issues never converging to `closed`), but the
gate has a side effect ADR-0006 did not need to consider at the time: it makes
`code_review` and `qa` **unreachable states** in memory.

Confirmed against the code: `set-status` dispatch (`solomon_harness/github.py:
719-726`) calls `record_transition(...)` for every column, but
`record_terminal_status(...)` — the only function that touches the issue
row's `status` field — only when `args.status == "Done"`
(`solomon_harness/github.py:719-726`). `record_transition`
(`solomon_harness/github.py:527-570`) writes exclusively to the append-only
`transitions` table and the `board_history:*` JSON blob; it never touches the
issue row. So a card that moves `In Progress` -> `Code Review` -> `QA` ->
`Done` leaves the memory row frozen at `in_progress` (the last status
`/solomon-start` wrote) for the entire review and QA phase. Every
memory-only consumer that needs to distinguish "coding" from "in review" or
"in QA" — the cockpit read port, the session-start digest, the loop — cannot,
because the token is never written.

Issue #173 (AC1) requires ungating the write-through so every board
transition writes the canonical token through. Its AC3 requires a one-shot
pass over existing rows so no non-canonical (display-name or mixed-case)
status value survives in the store. AC3 sits on top of the exact rejection
ADR-0006 made at decision point 1 (1c) — this ADR has to explain why a
narrowly scoped version of that rejected option is now the right call, not
overturn the rejection wholesale. AC2 — that `log_issue` normalizes whatever
status string it is given — is **already satisfied**: `normalize_status`
(`solomon_harness/tools/database_client.py:96-146`) is called unconditionally
inside `log_issue` (`solomon_harness/tools/database_client.py:2401-2434`) for
every write, including the ones this ADR adds. No new work is needed for AC2;
it is a byproduct of ADR-0006's decision point 1, not of this change.

## Decision drivers

- Reachability: every canonical token (`in_progress`, `code_review`, `qa`,
  `closed`) must be a state some memory row can actually hold, not only the
  terminal one.
- Single seam over distributed discipline: the fix must not depend on every
  present and future caller remembering to do the right thing.
- Preserve ADR-0006's constraints on the write-through: `log_issue` keeps its
  5-arg contract and full-replace UPSERT semantics; the write stays
  best-effort and MUST NOT raise on the dispatch path that every board move —
  not only Done — now runs through.
- Preserve ADR-0006's non-destructive migration stance: any bulk pass over
  existing rows must go through the same contract-preserving path as a live
  write, not a bespoke destructive rewrite.
- Reconcile (ADR-0006 decision point 3a, GitHub as source of truth) is
  untouched and remains the terminal-status convergence backstop; this ADR
  does not change who is the source of truth or how divergence is repaired.

## Considered options

Decision point 1 — generalizing the write-through (amends ADR-0006 decision
point 2, option 2b's gate):

- (a) Ungate `set-status` dispatch: call a generalized status write-through
  unconditionally for every `args.status`, at the same seam that already
  calls `record_transition` unconditionally.
- (b) Keep the `Done` gate as-is; have each `/solomon-*` command markdown
  file that moves a card to `Code Review` or `QA` call `log_issue` itself,
  directly, after invoking `set-status`.
- (c) Fold the status write into `record_transition` itself, so the one
  function that already runs on every transition also updates the issue row.

Decision point 2 — normalizing existing rows (a narrow exception to ADR-0006
decision point 1's rejection of option 1c):

- (a) A one-shot, idempotent, per-row read-modify-write pass: read each
  row, run its stored `status` through `normalize_status`, and write back
  only when the normalized value differs, through the unchanged 5-arg
  `log_issue` (same shape as the write-through and as `reconcile`).
- (b) No migration: rely solely on decision point 1's forward write-through to
  overwrite each row's status the next time its card moves.
- (c) The destructive option ADR-0006 already rejected as 1c: a bulk
  SQL/QL `UPDATE` against the stored column, independent of `log_issue`, with
  no per-row contract preservation.

## Decision outcome

Chosen: **(1a) + (2a)**.

**Decision point 1 — ungate the dispatch (1a).** The `set-status` seam in
`solomon_harness/github.py` (currently lines 719-726) already calls
`record_transition` unconditionally; it is the one place every caller funnels
through, whether that caller is an interactive CLI invocation or one of the
`/solomon-*` command markdown files shelling out to
`python -m solomon_harness.github set-status`. Generalizing
`record_terminal_status` into an unconditional status write-through at this
same seam means zero changes to any command file — every present and future
caller is covered by the one change, because none of them call `log_issue`
directly today (rejecting (b), which would require finding and editing every
command file that moves a card to `Code Review` or `QA`, duplicate the
read-modify-write and the STRIDE-safe exception handling at each site, and
silently regress the moment a new command or a manual `set-status` invocation
is added without the extra call — reachability would only be as strong as the
discipline of remembering it every time). It also keeps the write concerned
with exactly one thing at each layer (rejecting (c): `record_transition`
appends to an immutable timeline and a JSON blob; the issue row's `status` is
a mutable current-snapshot field. Folding the status write into
`record_transition` would conflate an append-only log with a point-in-time
field, make the timeline write no longer trivially idempotent to reason
about, and complicate the one behavior that is genuinely `Done`-specific —
assignee capture on delivery — which would need special-casing inside a
function whose contract is otherwise "append a transition row", not
"maintain the issue snapshot").

Concretely, `record_terminal_status` generalizes along a single axis: instead
of hardcoding `"closed"`, it writes `normalize_status(args.status)`. This
needs no separate branch for the terminal case, because `normalize_status`
already maps the board display name `"Done"` to `"closed"` via the existing
`_STATUS_ALIASES` table (`solomon_harness/tools/database_client.py:96-146`).
The one behavior that stays terminal-specific — capturing the assignee when
absent — becomes conditional on `is_terminal(normalized_status)` rather than
on the literal string `"Done"`, so it still fires only at delivery. Every
other ADR-0006 constraint on this write is unchanged: it reads the current
row, preserves title/type/milestone/assignee, writes through the unchanged
5-arg `log_issue` (UPSERT on `github_id`), and is best-effort — the broadened
`try`/`except` still catches every exception and logs only
`type(exc).__name__`, never `str(exc)`, so a backend failure on an
`In Progress` or `Code Review` move can no longer break that board move than
a `Done` move could break a merge before this change (STRIDE: information
disclosure and denial of service controls both carry over unmodified).

On the hexagonal-dependency-inversion note ADR-0006 already made: a board
adapter (`github.py`) taking a dependency on the memory store inverts the
default where adapters do not call each other. This ADR does not introduce
that inversion — it extends the one ADR-0006 already accepted and scoped
narrowly, widening which `set-status` calls exercise the existing coupling
rather than adding a new coupling or a new direction. The call remains fully
reversible (delete the generalization and `reconcile` remains the backstop
for terminal rows, exactly as before); non-terminal rows would then simply
return to being unreachable, which is the bug this ADR fixes, not a new risk.

**Decision point 2 — one-shot normalization, narrowly scoped (2a).**
ADR-0006 rejected 1c — "destructively rewrite all stored rows... in a
one-shot migration" — because an ad hoc bulk rewrite risks corrupting the
source of truth with no path back and no guarantee of preserving fields the
rewrite does not intend to touch. The pass AC3 requires is not that option:
it is a per-row, idempotent read-modify-write that runs each row's `status`
through the exact same `normalize_status` function every live write already
uses, through the exact same 5-arg `log_issue` UPSERT, changing only the
`status` token and leaving `title`/`type_`/`milestone_id`/`assignee` byte-
identical to what was read. It writes only when the normalized value differs
from the stored value, so a second run performs zero writes — the same
idempotency guarantee `reconcile` (ADR-0006 decision point 3a) already
established for terminal convergence. Framed this way, the pass is
non-destructive in exactly the sense ADR-0006 cared about (data safety, an
unchanged write contract, no bespoke SQL); it does rewrite stored status
values in bulk, but through the same narrow, audited path as any other
write, not around it. (b) is rejected because rows whose cards never move
again — permanently open cards, or rows already written before this ADR —
would carry mixed-case or display-name tokens forever, which is exactly what
AC3 rules out and what motivated defining a canonical vocabulary in the first
place (ADR-0006 decision driver 1). (c) remains rejected for the reasons
ADR-0006 already gave; this ADR does not reopen that rejection, it carves out
a path that was never what 1c described. The pass targets the same backend
`reconcile` does — the shared SurrealDB store only, warning and skipping on a
SQLite fallback rather than half-repairing a per-worktree store (ADR-0006
RAID R1) — reusing that targeting discipline rather than establishing a new
one.

### Consequences

- Positive: `code_review` and `qa` become reachable states — every board
  transition, not only `Done`, converges the memory row to the board within
  the same best-effort, non-raising guarantee `Done` already had; the
  cockpit, the session-start digest, and the loop can now distinguish
  "coding" from "in review" from "in QA"; the fix lives at one seam, so no
  command file needs to change and no future caller can silently regress it;
  the one-shot pass clears legacy display-name and mixed-case rows without
  a new write path to audit — it is the existing write-through's
  read-modify-write shape, run once over the backlog.
- Negative: `set-status` now performs a memory read-modify-write on every
  board move, not only on `Done` — more frequent, still best-effort, still
  bounded by the same try/except that already existed for the terminal case;
  a memory outage that used to only stall a `Done` write-through can now
  also (harmlessly, since it is caught) stall an `In Progress`/`Code
  Review`/`QA` write-through, leaving that row briefly stale until the next
  transition or a future reconcile-style repair; the one-shot pass is a bulk
  operation against the shared store and needs the same operational care
  `reconcile` already gets (run from a fresh process, per bug #37's dead MCP
  socket note in ADR-0006's follow-ups).
- Follow-ups: `reconcile` (ADR-0006 decision point 3a) is unchanged and
  remains scoped to terminal-status convergence against
  `gh issue list --state all`; it does not need to grow non-terminal
  awareness because the forward write-through now covers non-terminal
  transitions directly. The one-shot pass is a maintenance operation, not a
  standing service — implementation should expose it the same way
  `reconcile` is exposed (a `dry-run`-capable CLI subcommand under
  `solomon_harness/cli.py`, per the existing `memory reconcile` command),
  so it can be re-run safely if a future alias is added to
  `_STATUS_ALIASES` without needing a bespoke script each time.

## More information

Amends ADR-0006 (`docs/adrs/0006-canonical-issue-status-vocabulary-and-
board-to-memory-write-through.md`), decision points 1 and 2; decision point 3
(reconcile, GitHub as source of truth) is unaffected and cited here as the
precedent for this ADR's idempotency and shared-store-only targeting.
Realizes issue #173's AC1 (ungate the write-through) and AC3 (one-shot
normalization); AC2 was already satisfied by ADR-0006 decision point 1 and
required no change. Code referenced: `solomon_harness/github.py:719-726`
(dispatch), `:610-654` (`record_terminal_status`), `:527-570`
(`record_transition`); `solomon_harness/tools/database_client.py:96-146`
(`_STATUS_ALIASES`, `normalize_status`, `is_terminal`,
`STATUS_DISPLAY_COLUMNS`), `:2401-2434` (`log_issue`), `:1833`
(`reconcile`, the sibling idempotent maintenance pattern this ADR's one-shot
pass follows). This decision is also recorded in the project memory via
`save_decision`.
