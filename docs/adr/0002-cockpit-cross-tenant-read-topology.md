# ADR-0002: Cross-tenant read topology for the delivery cockpit

- Status: accepted
- Date: 2026-06-28
- Amended: 2026-06-29 — v1 velocity metric source (see Amendment below)
- Deciders: software_architect with dba; ratified by the maintainer
- Issue: #44 (gates #54, #55, #56, #57; #53 is decoupled)

## Context and problem statement

The cross-project delivery cockpit (#44) must answer cross-project and cross-user
delivery questions, but the harness deliberately isolates each project as its own
SurrealDB database inside the shared `solomon` namespace (tenant id derived from the
git remote in `home.derive_tenant`; SQLite fallback per worktree), so memory never
leaks between projects (`agents/AGENTS.md`, Memory layer). A read port already
exists: `DatabaseClient(harness_dir=...)` exposes per-tenant reads
(`get_open_issues`, `list_milestones`, `list_releases`, `list_handoffs`,
`list_decisions`, `list_loop_runs`, `get_latest_activity`).

Two schema facts bound the decision, confirmed against
`solomon_harness/tools/database_client.py`:

1. The `issues` table carries no assignee/user column, so a canonical cross-tenant
   person identity does not exist today (RAID A-04). This gates slices 2 and 3
   regardless of the topology chosen.
2. `status` is a current snapshot with no transition history (`closed_at` etc.), so
   velocity (#55), open/close-rate (#56), and burndown (#57) need a time series the
   store does not keep (RAID A-01).

Slice 1 (#53) reads each tenant directly and renders current status only; it is out
of scope of this ADR.

## Decision drivers

- R-01 (critical): per-tenant isolation must hold by construction; no store is ever
  merged or joined.
- Unblock slices 2-5 with minimal migration and maximal reversibility.
- p95 < 2s for up to 25 projects / 500 issues (R-06).
- A canonical cross-tenant person identity is required for slices 2-3 (A-04), and a
  metric source is required for slices 3-5 (A-01).

## Considered options

- (a) On-demand cross-tenant aggregation: a read port fans out to each tenant's
  `DatabaseClient`, reads per tenant, and composes the portfolio view in process.
  No store is merged; isolation holds by construction.
- (b) Shared central store for tasks/projects (the maintainer's original "single
  database" idea): one store every project also writes to. Trivial cross-project
  queries, but breaks isolation, needs a new access-control layer, and requires a
  write-path migration in every project.
- (c) CQRS-style derived read model / projection: per-tenant stores stay the system
  of record; a separate read-optimized aggregate is built and refreshed on events
  (handoff/delivery), rebuildable from the tenants. The cockpit queries the
  projection.

## Decision outcome

Chosen: **(a) on-demand cross-tenant aggregation**, paired with a small cross-tenant
identity contract, with **(c) recorded as the documented evolution path** behind the
same read port. Option (b) is rejected.

(a) is the only option that preserves the isolation principle by construction
(R-01), unblocks slices 2-5 with zero migration, and is the most reversible (swap or
delete the adapter; tenants never change). (a) and (c) are a sequence rather than
rivals: both keep per-tenant stores as the source of truth behind the same read
port, so adopting (a) now does not foreclose (c) — only what the port reads from
changes, not the cockpit code. (b) is rejected because it trades a one-time
convenience for a permanent violation of a stated design principle, a new
access-control burden the epic explicitly defers, and the lowest reversibility; the
same cross-user reporting outcome is reachable via (a) plus the identity contract
with no migration.

Coupled sub-decisions (ratified with this ADR):

- **Identity contract:** define a canonical person key (normalized email or handle)
  resolved in the aggregation composer, so cross-user views (#54, #55) have a stable
  subject. This is a new shared contract every per-user view depends on.
- **Metric source for v1:** compute velocity and open/close-rate from `created_at`
  plus current status (cheap, approximate, available now) rather than adding event
  capture immediately. Revisit minimal event capture before burndown (#57) if the
  approximation proves too lossy. (Amended 2026-06-29: v1 velocity now reads
  `board_history` instead of `created_at`; see the Amendment section below. The
  `created_at` approximation still stands for open/close-rate (#56).)

**Evolution trigger to (c):** adopt the projection when any holds — sustained
portfolios beyond the 25-project / 500-issue envelope, p95 < 2s starts failing under
(a), or cross-portfolio analytics outgrow per-request fan-out.

### Consequences

- Positive: isolation preserved by construction; no tenant migration; the cockpit
  read port is stable across an eventual move to (c); composes with the SPA read API
  in ADR-0003 (the API is a driving adapter over this read port).
- Negative: per-request fan-out cost grows with project count, needing
  bounded-concurrency reads and a per-project timeout/circuit (R-04, R-06);
  velocity/burndown are approximate until/unless event capture is added; the
  identity normalization is a new shared contract slices 2-3 depend on.
- Follow-ups: define the canonical person key (owner: dba with software_architect);
  decide event-capture vs approximation before slice 5; revisit (c) at the named
  trigger. Tracked in memory as the person-key/history follow-up.

## Amendment 2026-06-29: velocity metric source

- Issue: #55 (slice 3a, per-user velocity)
- Amends: the "Metric source for v1" sub-decision above, for velocity only.

This amendment refines which source v1 velocity reads. It does not reverse the
accepted decision: the cockpit still reads on demand through the same per-tenant
read port (option (a)), isolation still holds by construction (R-01), and no new
event-capture mechanism is added.

**Decision.** v1 per-user velocity — and the per-user activity series (#133) — is
computed from `board_history`, the real board transitions already captured by
`github.record_transition`, not from the `created_at` approximation the original
sub-decision named. The history is a per-card timeline stored under the memory key
`board_history:<issue_number>` as a JSON list of `{column, entered_at}` entries; the
`entered_at` of the entry whose `column` is the Done column is the delivery
timestamp a velocity count keys on. Counts are attributed to a person through the
canonical assignee person key (ADR-0012 / #118), then summed per person across
tenants by composition — read each tenant's history independently and add, never
join two stores (compose-never-join, R-01). This supersedes the `created_at`
approximation for the velocity metric only.

This is a same-source refinement, not new event capture: `record_transition` already
writes `board_history` on every harness `set-status`, so v1 reads an existing series
rather than adding one. Only what the read port reads from changes; the cockpit code
and the isolation principle do not.

**Named consequence — coverage limitation (must be surfaced, never silent).**
`board_history` exists only for issues whose transitions passed through the harness
`set-status` path. An issue dragged to Done directly on the GitHub board, or closed
before `record_transition` existed, has no tracked history and therefore no derivable
delivery timestamp. Such issues are EXCLUDED from the velocity count, and the
exclusion is reported per user as "N excluded (no tracked history)", so thin or
missing history degrades to a stated, auditable gap rather than a silently-wrong
number. `entered_at` is a naive local-time ISO string (no timezone offset; see
`record_transition`), so every window comparison must normalize both sides to one
clock basis before bucketing by period.

**Revisit trigger (unchanged).** Minimal event capture remains deferred to before
burndown (#57): if `board_history` coverage proves too lossy in practice, add the
minimal capture then. Open/close-rate (#56) is not bound by this amendment — at its
own refinement it may keep the `created_at` approximation or move to `board_history`.

## More information

Composes with ADR-0003 (web UI stack). Recorded in project memory via
`save_decision`. Backs RAID R-01, R-03, R-06, A-01, A-04, D-01 on #44.
