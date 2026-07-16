# Spec 297: filter claimed issues out of SessionStart suggestions

- Issue: #297 · Status: ready
- Date: 2026-07-16 · Author: product_owner

## Context

Raised by the 2026-07-16 four-specialist harness verification audit (qa / dba / loop_engineer / software_architect). The per-issue claim/lease system (#215, ADR-0027) added `ClaimStore.filter_unclaimed` as the shared port for keeping a claimed issue out of "start here" surfaces, and two read paths (`MemoryService.get_open_issues`, `github.list_open_issues`) already apply it.

## Problem

The SessionStart digest is exactly the seam that suggests next steps to the human, and it reads open issues through the raw `DatabaseClient.get_open_issues()` rather than either claim-aware wrapper. A claimed issue can therefore still be recommended by the digest, reopening the double-pick race #215 was built to close.

## Requirements

1. `gather_digest`'s open-issues read excludes any issue currently claimed by a session other than the one rendering the digest.
2. The filtering uses the same `ClaimStore.filter_unclaimed` port `MemoryService.get_open_issues` and `github.list_open_issues` already call — not a fourth, independent implementation.
3. A claim-store failure degrades the digest to the unfiltered issue list; it never blocks or crashes SessionStart, and stays within the existing per-call timeout budget.
4. A shared test fixture proves the three open-issues read paths agree on the same input set (parity), so a future filtering change cannot silently diverge across them.

## Implementation Pointers

- `solomon_harness/digest.py:353` (`gather_digest`) — current: `open_issues = _run_with_timeout(db.get_open_issues, timeout=0.5, default=[]) or []` reads the raw `DatabaseClient.get_open_issues()` with no claim filtering. Expected: after this raw read, filter `open_issues` through the same `ClaimStore.filter_unclaimed` port `memory_service.py:97-129` and `github.py:451-490` already share, keeping the existing 0.5s timeout budget and degrading to the unfiltered list on any claim-store exception (log a warning, never raise).
- `solomon_harness/cli.py:108` (`handle_run`) — constructs a bare `DatabaseClient(harness_dir=harness_dir)` and passes it straight to `gather_digest(harness_dir, db)` (`cli.py:138-141`); this is the SessionStart entry point that currently bypasses both existing claim-aware wrappers.
- `solomon_harness/memory_service.py:97-129` (`MemoryService.get_open_issues`) — the pattern to mirror: extract numeric `github_id`s, call `self._claim_store.filter_unclaimed(numeric_ids)`, keep non-numeric tracking rows unconditionally (never claimed), degrade to the unfiltered list inside a `try/except` that logs a warning.
- `solomon_harness/github.py:451-490` (`list_open_issues`) — the second existing instance of the same pattern, with a default-injected `GitClaimStore(workspace_root)` when no `claim_store` argument is passed; `digest.py` should accept or default-construct a `ClaimStore` the same way.
- `solomon_harness/claim.py:738` (module-level `filter_unclaimed`) and `:800-871` (`ClaimStore` Protocol / `GitClaimStore.filter_unclaimed`) — the shared port `digest.py` calls; no change to `claim.py` itself.
- `solomon_harness/tools/database_client.py:3287-3332` (`DatabaseClient.get_open_issues`) — confirmed raw, non-claim-aware primitive; correctly left unchanged. Claim filtering belongs at the wrapper/digest layer, not the storage primitive.

## Acceptance Criteria

```gherkin
Scenario: A claimed issue is filtered out of the digest
  Given issue #50 is claimed by another session and issue #51 is open and unclaimed
  When gather_digest renders the SessionStart digest
  Then only "Start development on Ready issue #51" is offered
  And issue #50 does not appear anywhere in the rendered digest

Scenario: Boundary — nothing is claimed, no regression
  Given every open issue is unclaimed
  When the digest renders
  Then every open issue appears exactly as it did before this fix
  And the set matches MemoryService.get_open_issues() and github.list_open_issues() over the same issues (parity)

Scenario: Boundary — everything is claimed
  Given every open issue is claimed by another session
  When the digest renders
  Then zero "Start development" suggestions appear
  And the digest still completes without error or a partial render

Scenario: Failure path — the claim store is unreachable
  Given the claim store raises when read (e.g., a corrupt or missing git ref)
  When the digest renders
  Then it still completes within its existing per-call timeout budget (0.5s)
  And it degrades to the unfiltered issue list rather than blocking or crashing
  And the degradation is logged, matching the existing degrade-and-log pattern in memory_service.py and github.py
```

## Verification

```bash
uv run pytest tests/test_digest.py -v
```

## Design Constraints

Degrade-safe: a claim-store outage must never block or slow the SessionStart digest beyond its existing per-call 0.5s timeout budget. Reuse the existing `ClaimStore` port rather than introducing a second filtering mechanism, so the three read paths can never diverge on how a claim is judged.

## Out of Scope

Changing `ClaimStore`/`filter_unclaimed` semantics — settled by #215/ADR-0027. `github.list_open_issues`'s own claim filtering — already correct, untouched. Broader digest rendering or layout changes — not requested.

## Traceability

- Issue: #297
- ADR: ADR-0027
- PR: #307
