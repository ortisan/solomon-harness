---
name: incremental-migration-and-delivery
description: Governs decomposing a large architectural change into strangler-fig slices, expand-migrate-contract schema evolution, branch-by-abstraction seams, and short-lived feature-flagged cutovers with N-1 backward and forward compatibility. Use when planning a schema migration, a service split, or any change too large to ship as one atomic, reversible step.
---

# Incremental Migration and Delivery

Deliver large architectural changes as a sequence of small, reversible, always-shippable steps instead of a big-bang rewrite, so the system stays releasable at every commit and a failed step rolls back without a data-loss event. Decompose the change into a migration spine, run old and new behaviour in parallel behind a seam, cut traffic over incrementally, and only retire the old path once the new one has proven itself in production. Big-bang rewrites fail because they couple a long no-release window to a single irreversible switch; every pattern here exists to break that coupling.

## Strangler fig pattern

Route requests through a facade that delegates to the legacy system, then move one capability at a time to the new implementation behind that same facade until the legacy system is dead and can be removed. The facade is the architectural seam; without it you cannot move a slice without touching callers.

- Place the seam where you already own routing: an API gateway, reverse proxy, or a thin application-layer facade. The interface the facade exposes is a design contract (see `design_contracts_as_component_boundaries`); it must not change while you strangle, or every caller becomes part of the migration.
- Migrate by vertical slice (one endpoint, one bounded context, one event type), not by horizontal layer. A half-migrated layer leaves no slice fully on the new path and so nothing can be retired.
- Record the cutover order and the rollback trigger for each slice as a decision via `save_decision`, and link the ADR (see `architectural_decision_records`). The strangler runs for weeks to quarters; the next agent must read why slice N precedes slice N+1.
- Define the exit condition up front: legacy call count for the migrated slice at zero for a defined soak (for example 14 days), then delete the legacy code in the same release. A strangler with no kill date becomes permanent dual-maintenance.
- Shared mutable state is the hard case. If old and new both write the same store, decide who owns the write before you split reads, or use expand-contract (below) on the schema first.

## Expand-contract (parallel change)

The only safe way to evolve a schema, API, or message contract that has live producers and consumers you cannot deploy atomically. Three ordered phases, each independently deployable and reversible.

- Expand: add the new shape additively. New nullable column, new optional field, new endpoint version, new event field. Nothing reads it yet. This phase is always backward compatible by construction.
- Migrate: dual-write to old and new, backfill historical rows in batches, then move readers to the new shape. Keep writing both until every reader is confirmed on the new shape.
- Contract: stop writing the old shape and remove it, only after telemetry proves zero readers and zero writers remain on the old path.

```sql
-- Expand: additive, deployable while old code still runs
ALTER TABLE orders ADD COLUMN customer_ref uuid NULL;

-- Migrate: backfill in bounded batches (never one unbounded UPDATE that locks the table)
UPDATE orders SET customer_ref = legacy_customer_id::uuid
WHERE customer_ref IS NULL AND id BETWEEN :lo AND :hi;

-- Contract: only after all writers populate customer_ref and all readers use it
ALTER TABLE orders ALTER COLUMN customer_ref SET NOT NULL;
ALTER TABLE orders DROP COLUMN legacy_customer_id;
```

- Never rename in place. A rename is a destructive expand and contract fused into one irreversible step; split it. Never add a `NOT NULL` column with no default in the expand phase against a populated table, it fails the deploy.
- Each phase is a separate release with its own rollback. Treat the gap between phases as deliberate: you may sit in dual-write for days while you watch metrics.
- For online schema changes on large tables (>~1M rows) under load, use a non-blocking tool: `gh-ost` or `pt-online-schema-change` for MySQL, native concurrent operations plus `CREATE INDEX CONCURRENTLY` for Postgres, or the platform's online-DDL. A naive blocking `ALTER` is an outage.
- API evolution follows the same arc: add fields as optional, version only on a true breaking change (see `rest_api_design`), and overlap old and new versions through a published deprecation window before contract.

## Branch-by-abstraction

The technique that lets expand-contract and strangler live on trunk without a long-lived feature branch. Introduce an abstraction over the thing you are replacing, point all callers at the abstraction, build the new implementation behind it, switch, then remove the abstraction.

1. Create an interface (the design contract) that captures how callers use the legacy component.
2. Route every caller through it, with the legacy implementation as the only binding. Ship. The system is unchanged but now has a seam.
3. Build the new implementation behind the same interface, exercised by tests and a dark launch.
4. Flip the binding (often a flag, see below). Run both available so you can flip back instantly.
5. Delete the old implementation and, if it has no further value, the abstraction itself.

Prefer this over a long-lived migration branch: it keeps the change integrating into trunk continuously, which is what makes the SRE progressive-delivery pipeline able to ship it. A multi-week branch defers all integration risk to a single merge, which is the big-bang failure mode wearing a different hat.

## Feature flags and dark launches

Flags are the runtime switch that decouples deploy from release and gives every step an instant, no-redeploy rollback. Match the flag's lifespan to its job.

- Release/migration flags are short-lived kill switches for one cutover. Default off, flip on for a ramp, then delete the flag and the dead branch within one or two sprints. Track each open release flag as an issue via `log_issue` so it is not orphaned; a stale flag is dead conditional code and a latent incident.
- Operational flags (kill switches, load-shedding toggles) are long-lived and owned by SRE; they pair with the circuit breakers and bulkheads in `resilience_patterns`.
- Experiment flags drive A/B allocation and belong to product analytics, not migration.
- Dark launch: send real production traffic to the new path with its result discarded or shadow-compared against the old path, so you measure correctness and load before any user depends on it. Shadow reads are cheap; shadow writes need an isolated store or idempotent, clearly-namespaced effects so they never touch real customer state.
- The actual traffic ramp (1% -> canary -> 50% -> 100%, with automated metric gates and rollback) is owned by the SRE `release_engineering_and_progressive_delivery` skill. This skill decides the seam and the flag; that skill drives the percentage and the abort criteria. Hand the cutover plan over with `log_handoff` and persist the migration state with `save_session` so the executing agent resumes mid-ramp with full context.

## Backward and forward compatibility

Incremental delivery means two versions of your code run at once during every rollout and rollback. Each step must be compatible in both directions or the rollback itself becomes an outage.

- Backward compatible: new code reads data and messages written by old code. Forward compatible: old code tolerates data and messages written by new code, typically by ignoring unknown fields. Expand-contract gives you both for free if you never read a field in the same release that first writes it.
- Enforce the "old reader ignores unknown fields" rule at the serialization layer: Protobuf and Avro give it by design; for JSON, reject strict/closed-schema validators on the read path during a migration. A consumer that 500s on an unknown field blocks the producer's rollout.
- N-1 compatibility is the contract for rolling deploys: version N must interoperate with N-1 in both directions, because during the roll both are live. Never ship a change that requires all instances to update atomically.
- Migrations must be expand-only within a release. A release that both adds and drops a column cannot be rolled back, because rolling back the code leaves the schema ahead of it.
- For events and queues, version the schema and keep consumers tolerant; a poison-message path that rejects a new-but-valid event will halt the whole stream.

## Common pitfalls

- A rename done in place (column, field, endpoint) instead of expand-contract: it is an irreversible fused add-and-drop. Reject it.
- A single release that adds the new shape and removes the old one, leaving no rollback because the code and schema can no longer disagree safely.
- Reading a new column or field in the same deploy that first writes it, so a rollback or an N-1 instance hits data that does not exist yet.
- Backfilling with one unbounded `UPDATE`/`ALTER` that locks a large table under load; batch it or use an online-DDL tool.
- A long-lived migration branch instead of branch-by-abstraction on trunk, deferring all integration risk to one merge.
- A strangler facade whose exposed contract drifts during the migration, pulling every caller into the change.
- A strangler or feature flag with no kill date, becoming permanent dual-maintenance and dead conditional code.
- Dark-launch shadow writes that touch real customer state instead of an isolated or idempotent namespace.
- A strict/closed JSON schema validator on the read path that rejects unknown fields and blocks the producer's rollout.
- Owning the traffic ramp and abort gates inside this design step instead of delegating them to the SRE progressive-delivery pipeline.

## Definition of done

- [ ] The change is decomposed into independently deployable, individually reversible steps, each shippable on trunk; no long-lived migration branch.
- [ ] A seam exists (strangler facade or branch-by-abstraction interface) defined as a stable design contract that does not change during the migration.
- [ ] Every schema/API/message change follows expand-migrate-contract; no in-place renames; the contract phase runs only after telemetry proves the old path has zero readers and writers.
- [ ] Each release is N-1 compatible in both directions; expand-only within a release so any single step rolls back cleanly.
- [ ] Backfills are batched or use a non-blocking online-DDL tool appropriate to the datastore and table size.
- [ ] The cutover is gated by a short-lived feature flag with a recorded default, owner, and deletion date tracked via `log_issue`; new behaviour is dark-launched/shadow-compared before any user depends on it.
- [ ] The traffic ramp, metric gates, and automated rollback are delegated to the SRE `release_engineering_and_progressive_delivery` skill; the cutover plan and live migration state are handed over via `log_handoff` and `save_session`.
- [ ] Cutover order, rollback triggers, and the legacy kill date are recorded with `save_decision` and linked to the ADR; the legacy code is deleted in the release that closes the soak window.
