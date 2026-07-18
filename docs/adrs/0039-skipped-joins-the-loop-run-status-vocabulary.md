# ADR-0039: "skipped" joins the closed loop-run status vocabulary

- Status: accepted
- Date: 2026-07-17
- Deciders: loop_engineer, software_architect (PR #348 review round 1)
- Issue: #347

## Context and problem statement

ADR-0016 closed the loop-run status vocabulary to `{ok, failed}` and compiled it into a live SurrealDB field ASSERT, so a writer and the store can never disagree on a token (#165). The no-op detection feature (#347) needs a third outcome the exit code cannot express: a zero-exit start that changed nothing. Writing `"skipped"` without amending the vocabulary is rejected by the ASSERT on the primary backend and silently swallowed by the best-effort ledger writer — the exact silent-vanishing bug class ADR-0016 exists to prevent, verified live during review.

## Decision drivers

- The vocabulary is a machine-enforced closed set; extending it is an ADR-owned decision, not an implementation detail.
- The metric contracts must stay truthful: a skipped run is not a failure and not a delivery.

## Considered options

- Amend ADR-0016: add `skipped` to `LOOP_RUN_STATUSES` (the ASSERT regenerates from the tuple).
- Reuse an existing token (`ok` with a decision note, or `failed`) — misrecords the outcome the feature exists to distinguish.
- Record skips outside the ledger — splits the run log into two stores.

## Decision outcome

Chosen option "amend ADR-0016": `LOOP_RUN_STATUSES = ("ok", "failed", "skipped")`. `skipped` marks a zero-exit start whose workspace snapshot shows no branch-ref movement and no working-tree change and whose issue is not PR-protected. Metric semantics, decided here: `loop_run_failure_rate` keeps counting only `failed`/legacy `failure`, so skipped runs are non-failures in the numerator but remain in the denominator; `loop_run_throughput` counts all rows and therefore remains an attempt-count, not a delivery-count.

Migration mechanism: the five ASSERT-bearing status/state fields switch from `DEFINE FIELD IF NOT EXISTS` to `DEFINE FIELD OVERWRITE`. `IF NOT EXISTS` is a no-op on a pre-existing field, so a database created before a vocabulary grew keeps the old closed ASSERT and rejects the new token forever — verified live: on a database whose `loop_runs.status` field was defined with `['ok','failed']`, re-applying the `['ok','failed','skipped']` definition with `IF NOT EXISTS` left the old ASSERT in place and `CREATE loop_runs SET status='skipped'` was still rejected. `OVERWRITE` re-applies the current vocabulary on every connect (idempotent when unchanged, corrective when the set grew) and still rejects genuine garbage. This makes every typed-state field self-healing, so future vocabulary growth reaches existing tenants without a manual migration.

### Consequences

- Positive: the skipped outcome lands on the primary backend, including pre-existing tenant databases; writer, schema, and aggregators agree on the token set; every typed-state field now migrates its own vocabulary on connect.
- Negative: consumers that assumed a two-token vocabulary must treat unknown-to-them tokens as non-failures; the throughput metric's attempt-count semantics are now load-bearing and documented; `OVERWRITE` rewrites the field definition on every connect (negligible cost, five statements).
- Follow-ups: none — the aliases table gains no entries (`skipped` has no legacy spellings).

## More information

Amends ADR-0016 (its vocabulary table now lists `skipped`). Shipped with #347 in PR #348; enforced by `tests/test_loop_run.py` (canonical tuple, write-seam round-trip, failure-rate filter exclusion).
