# Spec 369: Add opt-in behavioral benchmark for generated subagents

- Issue: #369 · Status: ready
- Date: 2026-07-18 · Author: product_owner, ml_engineer, software_engineer

## Context

Parent #171 compares the runtime policies available to generated subagents. The
structural checks delivered so far prove that generated files and delegation cues
exist, but they do not show whether a model, effort, or tool-policy change improves
reproducible task outcomes. This first dependency slice creates the evidence needed
by follow-up issues #370 and #371 without activating either policy.

## Problem

The harness cannot compare two generated-subagent configurations against the same
versioned tasks. A maintainer therefore has no local, auditable quality, latency,
or cost baseline for accepting or rejecting later tool, model, and effort changes.

## Requirements

1. Define a versioned golden set with at least nine unique cases covering happy,
   boundary, and failure paths for planning/read-only, implementation, and review.
2. A qualifying pilot has exactly the `baseline` and `candidate` arms and exactly
   three repetitions for every case-arm pair; the nine-case pilot therefore yields
   exactly 54 normalized results.
3. The active host owns all model invocation and supplies bounded, recorded run
   artifacts. Preparation, scoring, comparison, and serialization remain local,
   deterministic, offline, and free of provider SDKs and subprocess execution.
4. Closed, versioned JSON contracts reject unknown fields, unsafe paths, symlinks,
   non-positive budgets, oversized inputs, duplicate run identities, and incomplete
   comparisons before emitting an eligibility verdict.
5. Every result identifies the golden-set and case versions, arm, repetition,
   agent-content and effective-policy digests, reported host/provider, reported
   model/version, effort, verdict, first failed assertion, duration, raw-artifact
   pointer, and every available usage/cost field.
6. Unsupported usage fields remain explicit `null` values. They are never inferred
   and never converted to zero.
7. Structural scoring covers required and forbidden artifacts/actions, expected
   exit status, and protected-state snapshots. A prohibited mutation attempt fails
   the isolation assertion, and preparation of a later run always starts in a new
   scratch directory.
8. Comparison reports pass rates and p50/p95 duration per arm. Any candidate
   failure on a case that passed all baseline repetitions is named as a golden-case
   regression and makes eligibility false, even when aggregate pass rates match.
9. At least 95 percent of host-exposed usage records are attributable to one run
   identity. Median scoring and normalization overhead stays below one percent of
   recorded host wall time on the 54-run fixture corpus.

## Implementation Pointers

- `solomon_harness/evals.py:58-202` currently validates agent files, configuration,
  and memory only. Keep that shared suite offline and unchanged in purpose.
- Create `solomon_harness/behavioral_evals.py` as a functional core with frozen
  manifest, artifact, result, and comparison models; strict JSON parsing; canonical
  digests/serialization; bounded scratch preparation; deterministic structural
  scoring; completeness checks; percentiles; and a small `python -m` adapter whose
  invalid/incomplete paths return non-zero. The module must import no provider SDK,
  open no network connection, execute no subprocess, and touch neither project
  memory nor GitHub.
- Reuse the anchored, no-follow path discipline in
  `solomon_harness/secure_paths.py:1-157` for fixture reads and scratch writes.
  Treat recorded actions as inert data and never execute them.
- Create `tests/test_behavioral_evals.py` with contract-linked tests for manifest
  bounds, 54-result scoring, default-off behavior, incomplete comparison, isolation,
  missing telemetry, aggregate-hidden regression, deterministic output, attribution,
  and scoring overhead.
- Create `tests/fixtures/behavioral_evals/` with the ready manifest, nine seed cases,
  and a complete recorded two-arm corpus. The corpus intentionally contains one
  candidate regression and one offsetting candidate improvement so the per-case
  guard is exercised while aggregate pass rates remain equal.
- Add `docs/behavioral-evals.md` for the offline prepare/score/compare workflow,
  JSON compatibility rule, host-containment precondition, and the warning that this
  directional pilot does not activate routing.
- Record the host/scorer boundary in
  `docs/adrs/0043-host-controlled-behavioral-evaluation.md`; it follows ADR-0010's
  host-owned model loop and ADR-0024's deterministic local-processing policy.
- `solomon_harness/workflows.py:130-164` and
  `solomon_harness/cockpit_read.py:885-924` are context only. This slice does not
  write delivery metrics or couple comparison to the cockpit.

## Acceptance Criteria

### AC-EVAL-01: Complete pilot

```gherkin
Scenario: Score a complete two-arm pilot
  Given a versioned manifest with 9 valid cases, a baseline, a candidate, and 3 repetitions
  When the active host supplies the 54 bounded run artifacts and the scorer processes them
  Then exactly 54 per-repetition results are produced
  And every result identifies case version, arm, repetition, agent-content digest, effective policy, host, model/version, effort, verdict, failed assertion, and duration
  And available input, output, cache-token, and reported-cost values are preserved
```

### AC-EVAL-02: Default-off boundary

```gherkin
Scenario: Normal development remains offline
  Given the normal compile command and the repository test suite
  When they run without explicit behavioral-eval preparation or scoring
  Then zero remote model calls are attempted
  And no paid evaluation artifact is created
```

### AC-EVAL-03: Incomplete manifest failure

```gherkin
Scenario: Reject an incomplete comparison
  Given one case-arm pair with fewer than 3 repetitions
  When comparison is requested
  Then comparison exits non-zero with the missing case, arm, and repetition count
  And no routing-eligible verdict is emitted
```

### AC-EVAL-04: Isolation failure

```gherkin
Scenario: Detect a prohibited mutation
  Given a recorded case attempts to change the source checkout, project memory, or GitHub state
  When structural assertions are scored
  Then the case fails with the violated isolation assertion
  And the protected state is unchanged
  And the next fixture starts from a fresh baseline
```

### AC-EVAL-05: Missing telemetry

```gherkin
Scenario: Preserve honest unavailable metrics
  Given a host does not expose cache tokens or reported cost
  When its result is normalized
  Then each unsupported field is stored as unavailable
  And quality and duration remain valid
  And no metric is inferred or fabricated
```

### AC-EVAL-06: Per-case quality guard

```gherkin
Scenario: Report a regression hidden by the aggregate
  Given a candidate aggregate pass rate equals the baseline
  But one case that passes in all baseline repetitions fails in a candidate repetition
  When the comparison is produced
  Then the candidate is marked as having a golden-case regression
  And the report names the case and failed assertion
  And eligibility is false
```

## Verification

```bash
uv run python scripts/spec-lint.py docs/specs/369-behavioral-subagent-evals.md
uv run pytest -q tests/test_behavioral_evals.py
uv run pytest -q tests/test_integrations.py tests/test_scaffold_agent.py
uv run ruff check solomon_harness/behavioral_evals.py tests/test_behavioral_evals.py
uv run mypy solomon_harness/behavioral_evals.py
uv run pytest -q
```

Manual check: prepare the nine-case manifest into a temporary directory, confirm
that no subprocess or provider call occurred, score the recorded two-arm corpus,
and inspect 54 results plus the named per-case regression and false eligibility.

## Design Constraints

- The issue body's acceptance criteria are canonical; this section mirrors them
  under ADR-0038's precedence rule.
- ADR-0010 C1 remains binding: the active host is the model loop. The scorer does
  not launch, schedule, cancel, or select model work.
- The host must confine a qualifying run to its prepared scratch directory, deny
  checkout/memory/GitHub writes, and report protected-state snapshots and denied
  attempts. The offline scorer validates that evidence but cannot undo or attest an
  external mutation performed before scoring; a host lacking containment evidence
  cannot produce a qualifying run.
- Inputs are untrusted data: strict schemas, anchored relative paths, no symlinks,
  explicit count/byte/prompt bounds, no credentials, and no execution of recorded
  actions.
- Schema changes are explicit and versioned. Identical accepted manifest and run
  evidence produces byte-identical normalized result/comparison JSON. A fresh scratch
  path is returned out of band and is not part of that canonical evidence.
- Merge, release, Done, tool-policy generation, and routing activation remain
  human-gated and outside this slice.

## Out of Scope

- Direct provider SDK calls or a repository-owned model loop.
- Tool-policy generation and activation, model/effort routing activation, or
  modification of generated agent configuration.
- LLM-as-judge, daemon, scheduler, autonomous stage selection, dashboard rendering,
  project-memory metrics, merge, release, or Done automation.
- Paid calls in normal tests or CI and claims of production-level statistical power.

## Traceability

- Issue: #369 (child of #171; blocks #370 and #371)
- ADR: docs/adrs/0043-host-controlled-behavioral-evaluation.md (planned in this branch)
- PR: pending
