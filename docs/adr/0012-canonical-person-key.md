# ADR-0012: Canonical person key — cross-tenant identity contract

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect with dba; security and product_owner consulted
- Issue: #118 (realizes the person-key follow-up deferred by ADR-0002; enabler for #54, #55; parent epic #44)

## Context and problem statement

Issues in the project memory carry no person. The model is
`issues (github_id, title, type_, status, milestone_id, created_at)` and the write
API is `log_issue(github_id, title, type_, status, milestone_id)`
(`solomon_harness/tools/database_client.py`); the read side
(`get_open_issues`, `list_issues`, the cockpit `cockpit_read.py`) exposes status and
counts but no subject. There is no way to ask "what is one person working on, and how
fast, across every project" from memory alone.

ADR-0002 chose on-demand cross-tenant aggregation and explicitly deferred the
canonical person key ("define a canonical person key (normalized email or handle)",
owner: dba with software_architect), tracked as the person-key/history follow-up but
never filed until #118. Epic #44 constrains all analytics to existing memory entities
and forbids reading live from GitHub at query time, so the assignee must be captured
into memory at sync/log time and the cockpit must read it from memory.

This is architecturally significant because the key is a new shared contract every
per-user view (#54, #55) depends on: the normalization, collision, and namespacing
rules outlive this issue. The forces in tension are cross-tenant stability (the same
human must map to one key across isolated tenant stores), correctness (distinct humans
must never collapse, and one human's two spellings of the same email must not split),
PII minimization (a security NFR — store as little about the person as possible), and
tenant isolation by construction (R-01 from ADR-0002 — no store is ever joined).

## Decision drivers

- Cross-tenant stability: the same person resolves to one key across tenants, so a
  per-user portfolio view is composable from per-tenant reads.
- No false merges and no false splits: deterministic, auditable normalization;
  distinct humans never collapse to one key, and one human never splits into two.
- PII minimization (security NFR, RAID R-04): persist only what the cockpit needs as a
  subject — the normalized key — never name, avatar, or other profile fields.
- Tenant isolation by construction (ADR-0002 R-01): the key is computed and stored
  within each tenant store; portfolio reads are composed per tenant, never joined.
- Reuse the established on-write normalization precedent (ADR-0006 `normalize_status`)
  rather than invent a second consistency mechanism.
- Expand/contract, reversible migration: the field is nullable and additive; no
  existing 5-arg `log_issue` caller breaks and old rows still read.

## Considered options

Decision point 1 — when the key is computed:

- (1a) Compute on write. Normalize the assignee to the canonical key at the capture and
  `log_issue` seam, and store the normalized key on the issue row, mirroring the
  on-write `normalize_status` precedent already set by ADR-0006 in
  `database_client.py`.
- (1b) Compute on read. Store the raw assignee (handle and/or email) and normalize in
  the cockpit aggregation composer, as ADR-0002 originally sketched ("resolved in the
  aggregation composer").
- (1c) Hybrid: store the raw assignee and lazily materialize a derived key.

Decision point 2 — email-vs-handle precedence and namespacing:

- (2a) Email preferred over handle when both are known; a handle is namespaced as
  `gh:<lowercased-login>`; a null, absent, or malformed assignee yields a null key,
  queryable under the reserved pseudo-key `unassigned`.
- (2b) Handle preferred over email (the GitHub login is almost always present; email is
  commonly private).
- (2c) No namespacing: store handle and email in one flat key space.

Decision point 3 — matching strategy and what is persisted:

- (3a) Deterministic normalization only (lowercase and trim); persist only the
  normalized key.
- (3b) Fuzzy or probabilistic identity resolution (email-to-handle inference,
  display-name matching).
- (3c) Persist the full profile (name, avatar) alongside the key for richer views.

## Decision outcome

Chosen: **(1a) + (2a) + (3a)** — compute the canonical key on write, email preferred
with `gh:<login>` namespacing and a reserved `unassigned` pseudo-key, deterministic
normalization that persists only the key.

**Decision point 1 — compute on write (1a).** The key is normalized at the write seam
and the normalized value is stored on the issue row, alongside `normalize_status` in
`solomon_harness/tools/database_client.py`. This mirrors ADR-0006: placing
normalization below every consumer means the key cannot drift across the cockpit,
`digest.py`, and `evals.py`. Epic #44 already forces the assignee to be captured into
memory at sync time (no live GitHub read at query time), so normalizing at that same
seam is free. Rejecting 1b: resolving the key in the read composer would require the
read path to carry raw assignee data (more PII stored, against driver 3), recompute on
every read, and let each consumer drift if the composer logic ever forked — exactly the
divergence ADR-0006 removed for status. 1a keeps the read path a pure projection of an
already-canonical stored key. The accepted cost is that a wrong contract baked into
rows is expensive to undo (RAID R-02, high band), which is why this ADR pins the
contract before any capture code lands and gates capture behind green
`normalize_person_key()` tests. Rejecting 1c: a lazily materialized key carries both
costs — raw assignee stored and a second code path — for no benefit over 1a.

**Decision point 2 — email preferred, handle namespaced `gh:<login>` (2a).** Email is
the cross-tenant-durable identity: a person's email is the same string across projects
and tools, whereas a GitHub login is stable only within GitHub. So when an email is
known, the key is the lowercased, trimmed email. Email is frequently private through
`gh issue view --json assignees` (RAID A-01), so the handle path is the expected common
case, not the exception; a handle-only assignee yields `gh:<lowercased-login>`. The
`gh:` namespace puts every handle key in a key space disjoint from every email-form key,
so a handle can NEVER collide with an email by construction — even if a login string
ever looked email-like. A null, absent, or malformed assignee (empty email AND empty
login, or an object that fails to parse) yields a null person key, queryable under the
reserved pseudo-key `unassigned`. Rejecting 2b: preferring the handle would split one
human assigned by email in tenant alpha and by handle in tenant beta into two keys —
the exact split failure RAID R-02 guards against; email-preferred-when-known maximizes
the collapse of one human to one key across tenants. Rejecting 2c: a flat key space lets
a handle and an email theoretically collide, violating "distinct humans never collapse".

**Decision point 3 — deterministic only, persist only the key (3a).** Only
deterministic, auditable normalization is in scope; fuzzy or probabilistic identity
matching is explicitly out of scope. The store persists ONLY the normalized key — never
name, avatar, or other profile fields (security/PII NFR, RAID R-04). Rejecting 3b:
probabilistic matching is non-auditable and can collapse distinct humans, and #118 puts
it out of scope; the harness keeps deterministic, reviewable normalization. Rejecting
3c: storing profile data violates PII minimization; the cockpit needs a stable subject
key, not a profile.

### The identity contract (normative)

`normalize_person_key(email, login)` is the single function that defines the key. It is
total and deterministic:

- A known email yields `lowercase(trim(email))`.
- A handle-only assignee (login present, email absent or private) yields
  `"gh:" + lowercase(trim(login))`.
- When both an email and a login are known, the email wins.
- A null or absent assignee, or a malformed one (empty email AND empty login, or an
  object that fails to parse), yields a null person key. A null key is queryable under
  the reserved pseudo-key `unassigned`. No key is ever invented: on a parse failure the
  sync logs a warning carrying the exception type only (no store internals) and falls to
  `unassigned`; it must not raise.
- Determinism guarantees: identical inputs always yield identical keys; distinct emails
  never collapse to one key; one human's two spellings of the same email
  (`Alice@Example.com` and `alice@example.com`) collapse to one key (`alice@example.com`).
- `unassigned` is a reserved query token, never a valid concrete key: no real assignee
  can normalize to it.

### Consequences

- Positive: per-user cross-tenant views (#54, #55) get a stable subject from memory
  alone; the key is computed once at the write seam, so it cannot drift across the
  cockpit, digest, and evals consumers (the property ADR-0006 secured for status); PII is
  minimized — only the normalized key is persisted; tenant isolation holds by
  construction — the key is computed and stored within each tenant store and portfolio
  reads are composed per tenant, never joined (ADR-0002 R-01); the migration is
  expand/contract — a nullable, additive `assignee` field, so no existing 5-arg
  `log_issue` caller breaks and old rows read back as `unassigned`.
- Negative: because the key is computed on write, a wrong contract baked into rows is
  expensive to undo (RAID R-02), mitigated by pinning the contract here and gating
  capture behind green normalization tests; email is commonly private (A-01), so most
  keys are handle-form `gh:<login>`, which are stable within GitHub but would yield a new
  key if a person later switched GitHub accounts (accepted: the key follows the identity
  GitHub exposes, with no inference); no backfill of historical rows — rows written before
  this lands stay `unassigned` until their next sync re-writes them (accepted, A-03).
- Follow-ups: implement `normalize_person_key()` alongside `normalize_status` in
  `solomon_harness/tools/database_client.py`; add the nullable `assignee` field across the
  SQLite DDL and the SurrealDB UPSERT plus the optional `log_issue` parameter (dba +
  software_engineer); capture the assignee in the `solomon_harness/github.py`
  board-to-memory write-through (software_engineer); run the full Gherkin against both the
  SurrealDB primary and the SQLite fallback (RAID R-03). #54 (cross-user filter UI) and
  #55 (per-user velocity) consume this contract.

## More information

- ADR-0002 (`docs/adr/0002-cockpit-cross-tenant-read-topology.md`): chose on-demand
  cross-tenant aggregation and deferred this canonical person key; this ADR realizes that
  follow-up. The decision to compute on write (1a) refines ADR-0002's sketch of resolving
  the key in the read composer, for the drift and PII reasons above.
- ADR-0006 (`docs/adr/0006-canonical-issue-status-vocabulary-and-board-to-memory-write-through.md`):
  the on-write `normalize_status` precedent in `database_client.py` and the
  board-to-memory write-through in `github.py` that this capture extends.
- Epic #44 constraint: analytics use existing memory entities only, captured at sync
  time, never read live from GitHub at query time.

This decision is also recorded in the project memory via `save_decision`.
