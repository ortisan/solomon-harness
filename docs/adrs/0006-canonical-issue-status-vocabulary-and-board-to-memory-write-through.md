# ADR-0006: Canonical issue-status vocabulary and best-effort board-to-memory write-through

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect, software_engineer, product_owner
- Issue: #101

## Context and problem statement

On PR merge GitHub closes the linked issue via the `Closes #N` trailer, but no
delivery step writes the issue's terminal status back to the project memory store.
The only delivery seam, the `Done` board move in `solomon_harness/github.py`, never
calls `log_issue(..., status="closed")`, so the memory row stays frozen at its
pre-delivery value. Every memory-only consumer (`digest.py` resume digest,
Autonomous Mode `/solomon-loop`, `evals.py`, the cockpit read port) then diverges
from GitHub on every delivery, re-proposing or misreporting delivered work. A second
defect compounds it: `get_open_issues` filters the literal `status='open'`, a token
no lifecycle step actually writes, so the count is driven by stale and synthetic
rows rather than by real open work (`get_open_issues` returns 61 while
`gh issue list --state open` returns 37).

This is architecturally significant because it touches a contract three things
depend on at once: the token vocabulary stored for an issue's status, the semantics
of the "open" set that the loop and the cockpit read, and the direction and
consistency of the write that couples GitHub board state to the memory store. The
forces in tension are delivery availability (a memory write must never break a
merge), source-of-truth correctness (memory must converge to GitHub), and blast
radius (status is read by at least four consumers, and `log_issue` is a core write
method). The fix must be a non-destructive, expand/contract migration: reads stay
tolerant of legacy values while writes are normalized going forward.

## Decision drivers

- Single source of truth for the status vocabulary, derived from the existing
  `BOARD_COLUMNS`, so normalization and the open/terminal predicate cannot drift
  apart (addresses RAID R2/R3).
- Delivery availability over immediate memory consistency: a Done transition (the
  merge critical path) must never fail because the memory backend is momentarily
  unavailable.
- Bounded blast radius on a core write method: keep `log_issue`'s 5-arg contract and
  its full-replace UPSERT semantics unchanged.
- Reversible, non-destructive migration: normalize on write, keep reads tolerant of
  legacy display values, no destructive rewrite of stored rows.
- Convergence must be guaranteed and auditable even when the write-through is skipped
  (GitHub auto-close, backend outage, or a card that never passes through the CLI
  Done path).

## Considered options

Decision point 1 — where the status vocabulary lives and what "open" means:

- (1a) Define `normalize_status`, the terminal-literal set, `is_terminal`, and a
  token-to-display-column map once in the memory adapter (`database_client.py`),
  keyed off `BOARD_COLUMNS`; `log_issue` normalizes on write; `get_open_issues`
  becomes a non-terminal predicate. Reads stay tolerant of legacy values.
- (1b) Leave the literal `status='open'` filter and have each consumer
  (digest, evals, cockpit, loop) apply its own ad hoc terminal test.
- (1c) Destructively rewrite all stored rows to the canonical vocabulary in a
  one-shot migration and keep the literal filter.

Decision point 2 — the board-adapter to memory-store write coupling:

- (2a) Change `log_issue` to a status-only signature with `UPSERT ... MERGE` so the
  write-through is a single status-only call.
- (2b) Best-effort terminal write-through at the CLI `set-status` dispatch, gated on
  `status == "Done"`, alongside the existing `record_transition`, read-modify-writing
  through the unchanged 5-arg `log_issue`; it must never raise on the merge path
  (catch + log a warning).
- (2c) Make the write-through strict (raise on failure), rolling back the merge if
  memory cannot be written.

Decision point 3 — how divergence converges and who is the source of truth:

- (3a) Idempotent `reconcile` (memory against `gh issue list --state all`) that sets
  each GitHub-CLOSED issue's memory row to terminal and leaves GitHub-open rows
  untouched; GitHub is the source of truth, memory mirrors it, never the reverse.
- (3b) No backstop: rely solely on the write-through, accepting permanent drift for
  any card that bypasses the CLI Done path.
- (3c) Bidirectional sync that also pushes memory state back to GitHub.

## Decision outcome

Chosen: **(1a) + (2b) + (3a)**.

**Decision point 1 — canonical vocabulary in the memory adapter (1a).** The single
source of truth for status tokens lives in `database_client.py`, keyed off
`BOARD_COLUMNS`. `log_issue` normalizes on write: `In Progress`/`in_progress` ->
`in_progress`; `Code Review`/`code_review` -> `code_review`; `QA`/`qa` -> `qa`;
`Done`/`done`/`closed` -> `closed`; `open`, `Ideas`, `Backlog`, `Ready` pass through.
`get_open_issues` is redefined: "open" is no longer a literal status filter but a
**non-terminal predicate**, where terminal = `{closed, done, Done}`. The consumer
blast radius is `digest.py`, `evals.py`, `cockpit_read.py`, and the loop; reads stay
tolerant of legacy values, so this is an expand/contract, non-destructive migration
(rejecting 1c's destructive rewrite, which would risk corrupting the source of truth,
and 1b, which would let the vocabulary and the predicate drift across consumers —
exactly the failure RAID R2/R3 call out). Placing the vocabulary in the adapter,
below every consumer, is the only option where normalization and the open/terminal
test cannot diverge.

**Decision point 2 — best-effort write-through at the Done seam (2b).** `github.py`
writes the terminal status through to memory on the Done transition, at the CLI
`set-status` dispatch, gated on `status == "Done"`, alongside the existing
`record_transition`. It is best-effort: it MUST NOT raise on the merge critical path
(catch the failure and log a warning). This is a deliberate consistency-versus-
availability trade-off — delivery availability is chosen over immediate memory
consistency — with convergence guaranteed by the idempotent reconcile of decision
point 3 (rejecting 2c, which would let a memory outage roll back a merge). The
write-through read-modify-writes through the **unchanged 5-arg `log_issue`** (UPSERT
on `github_id`): it reads the current row, then writes one `log_issue` with
`status="closed"` and the preserved title/type/milestone. This keeps `log_issue`'s
contract and its full-replace UPSERT semantics intact (rejecting 2a, whose status-only
`MERGE` signature would change a core write method for the whole codebase — a larger
blast radius than the bug warrants).

On the dependency direction: a board adapter (`github.py`) taking a dependency on the
memory store inverts the hexagonal default, where adapters do not call each other and
coordination lives in the domain. We accept it deliberately and scope it narrowly,
because this is not a new pattern but an **extension of the write-through-plus-
idempotent-reconcile pattern already established in ADR-0002 (memory resilience
model)** to a new seam: GitHub board state -> memory. ADR-0002 introduced a best-effort
write-through mirror whose divergence is healed by an idempotent `reconcile()`; this
ADR applies the same shape one seam over. The write-through goes through the same
unchanged `log_issue` UPSERT-on-`github_id` path, so it inherits that model's
idempotency rather than inventing a second consistency mechanism. The coupling is one
directed call on one transition, fully reversible (delete the call and the reconcile
remains the backstop), which we judged cheaper and clearer than routing a Done
transition through a new domain coordinator.

**Decision point 3 — reconcile as the convergence contract, GitHub as source of
truth (3a).** Memory mirrors GitHub, never the reverse (rejecting 3c's bidirectional
sync, which would make memory able to mutate the board and break the single source of
truth). `reconcile` compares memory against `gh issue list --state all` and sets each
GitHub-CLOSED issue's memory row to `closed`, leaving GitHub-open rows untouched; it
is idempotent (a second run performs zero writes) and repairs any drift the
best-effort write-through leaves behind (rejecting 3b, which would accept permanent
drift for cards GitHub auto-closes outside the CLI Done path). Reconcile targets the
**shared SurrealDB only**: on a SQLite-fallback DB it warns and skips the whole repair
rather than half-repairing a per-worktree store (RAID R1). The 57 synthetic
memory-only rows (`risk-*`, `dep-*`, `followup-*`, `45-M*`, `77-M*`, `gh-1`) have no
GitHub close path and are explicitly **out of scope**, deferred to a sibling chore;
acceptance for #101 is defined against the 4 real GitHub rows plus the 17 stale rows,
not the raw 61-vs-37 count.

### Consequences

- Positive: one canonical status vocabulary that normalization and the open/terminal
  predicate both derive from, so consumers cannot drift; delivered work becomes
  terminal in memory at the Done transition and falls out of `get_open_issues`,
  `digest.py`, the loop, `evals.py`, and the cockpit; a merge can never be broken or
  rolled back by a memory outage; divergence (from outages, GitHub auto-close, or
  non-CLI Done paths) is healed by an idempotent reconcile with GitHub as the
  unambiguous source of truth; the migration is non-destructive, so legacy rows keep
  reading correctly.
- Negative: a board adapter now depends on the memory store, a deliberate deviation
  from the hexagonal default, justified as a narrow extension of the ADR-0002 pattern;
  best-effort write means a momentary memory outage leaves a row at its pre-delivery
  value until reconcile runs (eventual, not immediate, consistency); a SQLite-fallback
  worktree is not repaired by reconcile and can stay divergent until run against the
  shared store (RAID R1, warned and skipped, not silently half-done); the broadened
  `get_open_issues` predicate changes output for four consumers, mitigated by the
  shared terminal constant and a per-consumer regression test (RAID R3).
- Follow-ups: the 57 synthetic memory-only rows need a close path so
  `get_open_issues` stops counting them — a sibling chore on the same
  `memory-source-of-truth` milestone, consuming this ADR's canonical predicate (RAID
  R4, D5). Reconcile must be run from a fresh process to avoid the dead MCP write
  socket of bug #37 (RAID I2), documented in the command help. Separately, this repo
  carries a pre-existing ADR-number hygiene problem — duplicate numbers at 0001, 0002,
  0003, and 0005 (two files each). That is a flagged, independent cleanup, not part of
  this change; ADR-0006 itself is uncontested (no other 0006 exists).

## More information

- ADR-0002 (cross-tenant read topology for the delivery cockpit,
  `docs/adrs/0002-cockpit-cross-tenant-read-topology.md`): the cockpit read port
  consumes `get_open_issues`/`list_issues`. ADR-0006 changes the status snapshot's
  vocabulary (canonical tokens) and the open-set semantics (non-terminal predicate)
  that ADR-0002 relies on. The snapshot-only, no-transition-history model of ADR-0002
  is unchanged: this ADR normalizes the token written and redefines which rows are
  "open"; it adds no `closed_at`/transition history and keeps status a current
  snapshot, so ADR-0002's metric-source and history follow-ups stand as written.
- ADR-0002 (memory resilience model — reconnect-then-fallback and a write-through
  mirror, `docs/adrs/0002-memory-resilience-model.md`): the precedent for best-effort
  write-through paired with an idempotent reconcile that heals SurrealDB/SQLite
  divergence. ADR-0006 extends that pattern from the memory mirror seam to the GitHub
  board state -> memory seam, reusing the same `log_issue` UPSERT-on-`github_id`
  idempotency and the same "warn on the fallback DB, repair the shared store" stance.

This decision is also recorded in the project memory via `save_decision`.
