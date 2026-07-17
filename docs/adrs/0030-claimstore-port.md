# ADR-0030: ClaimStore port

- Status: accepted
- Date: 2026-07-14
- Amended: ADR-0035 (2026-07-17) adds version snapshots and conditional release outcomes to the port.
- Deciders: software_architect, software_engineer
- Issue: #238

## Context and problem statement

`solomon_harness/claim.py` implements the per-issue claim/lease mechanics
(ADR-0027) as a set of module-level functions over git-ref CAS. Every consumer
(`memory_service.get_open_issues`, `github.list_open_issues`,
`github.merge_pr_and_close`, `workflows.run_stage`) imports the module directly
and calls its functions, so the claim mechanism is a concrete dependency
threaded through the application layer rather than a port behind which an
adapter sits. ADR-0027 named this a deferred follow-up (its own "More
information" section: "a ClaimStore port/hexagonal extraction ... is tracked
separately and intentionally deferred"), flagged again in the #215 review as
finding review-215-m12. The project's default architecture is hexagonal
(ports and adapters), and claim filtering/acquisition is exactly the kind of
cross-cutting application policy that should sit behind an interface, not be
baked into each caller.

## Decision drivers

- Hexagonal default: consumers should depend on a port, not a concrete module.
- No behavior change: the claim mechanism's git-CAS correctness (mutual
  exclusion, fail-closed reclaim, heartbeat, TTL) must stay exactly as
  verified by the existing suite.
- Testability: a consumer's test should be able to inject a fake claim store
  instead of patching `solomon_harness.claim.*` internals.
- Low migration risk: the git-ref CAS mechanics are working, reviewed code;
  the port must not require rewriting them.

## Considered options

- **Option 1: Full rewrite of claim.py into a class-based adapter**, moving
  all git-CAS logic into `GitClaimStore` methods and leaving only pure helpers
  at module level. Cleanest end state, but rewrites reviewed, race-tested code
  (`TestClaimConcurrency`'s real-race coverage) and risks reintroducing a
  concurrency defect for no functional gain.
- **Option 2: A `ClaimStore` Protocol plus a `GitClaimStore` adapter that
  delegates to the existing module-level functions.** The IO surface
  (acquire, release, refresh, get, fetch_all, filter_unclaimed, holder,
  pr_protected) becomes a `typing.Protocol`; `GitClaimStore` implements it as
  a thin pass-through to `claim_issue`, `release_claim`, `refresh_claim`,
  `get_claim`, `fetch_all_claims`, `filter_unclaimed`, `get_claim_holder`, and
  `has_active_pr_or_review`. Consumers depend on `ClaimStore` by default
  injection (`claim_store: Optional[ClaimStore] = None`, defaulting to
  `GitClaimStore`), so every existing call site stays backward-compatible.
- **Rejected: a class wrapping claim.py without a Protocol.** A concrete
  `GitClaimStore` with no interface would still let consumers depend on git-CAS
  specifics via type hints, forfeiting the substitutability a port exists for.

## Decision outcome

Chosen option: **Option 2**, because it establishes the port boundary ADR-0027
deferred while keeping the git-CAS implementation untouched: `GitClaimStore`'s
methods call the same module-global functions the existing test suite already
patches (`solomon_harness.claim.claim_issue`, `.release_claim`, etc.), so
delegation is transparent and behavior is byte-identical to calling the module
functions directly. Consumers now depend on `ClaimStore`, injected with a
default, not on `solomon_harness.claim` as a concrete module.

### Consequences

- Positive: `memory_service.MemoryService`, `github.list_open_issues`,
  `github.merge_pr_and_close`, and `workflows.run_stage` depend on the
  `ClaimStore` Protocol; a test or a future adapter (e.g. an in-memory store
  for integration tests) can be injected without patching `claim.py`
  internals. A `MemoryService` test now injects a fake `ClaimStore` and
  asserts `get_open_issues` filters by it with zero `solomon_harness.claim.*`
  patching, proving the seam.
- Positive: pure domain helpers (`get_current_session_id`,
  `parse_claim_commit_message`, `is_claim_active`,
  `CLAIM_HEARTBEAT_INTERVAL_SECONDS`, `CLAIM_TTL_SECONDS`) stay module-level,
  since they carry no IO and gain nothing from sitting behind a port.
- Negative: `GitClaimStore` is a thin delegation layer, not a self-contained
  implementation -- reading it means following the call into the matching
  module function. This is an accepted trade-off for the low-risk migration;
  a future pass can fold the module functions' bodies into the adapter
  directly if the module-level API is ever retired.
- Follow-ups: none outstanding. `workflows.run_stage` builds one
  `GitClaimStore` per claim gate and routes every IO call (get, pr_protected,
  acquire, refresh, release) through that instance; the malformed-ref recheck
  via `get_claim_ref` stays a direct module call since it is not part of the
  port surface (it exists only for that one recheck, not a general read path).

## More information

Resolves the deferred ClaimStore-port follow-up recorded in ADR-0027 and
review finding review-215-m12 (issue #238). Implemented in
`solomon_harness/claim.py` (`ClaimStore`, `GitClaimStore`),
`solomon_harness/memory_service.py`, `solomon_harness/github.py`, and
`solomon_harness/workflows.py`. This decision is also recorded in the
project memory via `save_decision`.
