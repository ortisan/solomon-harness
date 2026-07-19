# ADR-0043: Host-controlled behavioral evaluation with deterministic offline scoring

- Status: accepted
- Date: 2026-07-18
- Deciders: software_architect, software_engineer, ml_engineer
- Issue: #369

## Context and problem statement

Generated subagents have structural installation tests but no reproducible behavioral
baseline for deciding whether a later tool, model, or effort policy is safe to activate.
Issue #369 introduces versioned manifests, recorded host runs, normalized results, and
comparison reports that will become evidence inputs to #370 and #371. Once a maintainer
has paid for a 54-run pilot and recorded activation decisions against its digests,
changing the artifact semantics without compatibility would invalidate historical
comparisons.

ADR-0010 C1 requires the host tool to remain the model loop; a repository-owned Python
LLM runner must not return. ADR-0024 requires local analysis to be deterministic,
hermetic, and free of token cost. The new boundary must also distinguish what the
offline scorer can verify from what only the executing host can contain: the scorer can
validate recorded events and protected-state snapshots, but it cannot undo or attest an
external mutation already performed by a host with broad access.

## Decision drivers

- Preserve ADR-0010 C1 and keep all model invocation, cancellation, credentials, and
  provider availability under the active host.
- Produce provider-independent, byte-stable evidence that #370 and #371 can consume
  without coupling activation to the evaluation implementation.
- Fail closed on unsafe paths, unbounded inputs, malformed evidence, and incomplete
  comparisons while normal development and CI remain offline.
- Keep unavailable telemetry honest and distinguish it from an observed zero.
- Make per-case regression visible even when aggregate quality is unchanged.
- Hold median scoring and normalization overhead below one percent of recorded host
  wall time on the initial 54-run corpus.

## Considered options

1. Add a provider SDK and repository-owned model runner that prepares, invokes, scores,
   and compares the pilot.
2. Keep invocation host-controlled and add a versioned, deterministic offline
   preparation/scoring/comparison core.
3. Encode the pilot only as ad hoc pytest fixtures with no durable interchange schema.
4. Run evaluation through a new daemon or external evaluation service.

## Decision outcome

Chosen option 2: host-controlled invocation with a deterministic offline core, because
it is the only option that preserves the existing model-loop boundary while producing
auditable, reusable evidence for later policy decisions.

`solomon_harness.behavioral_evals` is a functional core with a small imperative
filesystem shell:

- Frozen domain models and closed parsers validate manifest, run-artifact, result, and
  comparison schemas. `schema_version` evolves the interchange contract independently
  from `golden_set_version`; unknown fields and unsupported versions fail closed.
- A qualifying manifest has the exact `baseline` and `candidate` arms, at least nine
  unique cases, exactly three repetitions for every case-arm pair, and positive explicit
  limits for prompts, files, bytes, duration, tokens, and reported cost.
- Preparation reads a trusted, bounded, symlink-free seed and creates a new scratch
  directory for each run identity. It never overwrites a prior fixture. It emits prompt,
  expected assertions, arm policy, and budget as inert host input; it invokes no model.
- The host is the sole owner of model execution and containment. A qualifying host must
  confine the run to the prepared scratch directory, deny checkout, project-memory, and
  GitHub writes, and report containment plus before/after protected-state evidence. A
  recording without that evidence is invalid.
- Scoring treats recorded files and actions as data and never executes them. A valid
  structural assertion failure, including a denied prohibited mutation attempt or a
  protected snapshot mismatch, produces a normal `fail` result rather than a parser
  error. The result carries a deterministic first failed assertion.
- Every normalized result is keyed by golden-set version, case id/version, arm,
  repetition, agent-content digest, and effective-policy digest, with reported
  host/provider, model/version, effort, duration, verdict, raw pointer, and optional
  input/output/cache tokens and cost. Unsupported optional metrics are JSON `null` and
  are never inferred.
- Comparison first proves the complete Cartesian matrix. Missing, duplicate, or
  unexpected identities return a structured `incomplete_comparison` error naming the
  case, arm, and observed repetition count; no comparison file or eligibility value is
  emitted. A complete comparison reports pass rate and p50/p95 duration per arm. Any
  candidate failure on a case that passed all baseline repetitions is listed as a
  golden-case regression and makes `eligible` false.
- Identical accepted manifest and run evidence produces byte-identical normalized
  result/comparison JSON. Validation, scoring, comparison, and serialization have no
  side effects. Preparation is the only mutating operation, its authority is limited to
  caller-selected scratch storage, and its fresh physical path is returned out of band
  rather than entering canonical evidence.
- The module imports no provider SDK, opens no network connection, executes no
  subprocess, and reads or writes neither project memory, GitHub, workflow state, nor
  generated-agent configuration. Its module CLI only adapts local files to the same
  domain operations and maps the closed error set to non-zero exits.

The closed error codes are `invalid_manifest`, `unsupported_schema`, `unsafe_path`,
`limit_exceeded`, `invalid_artifact`, and `incomplete_comparison`. Adding a field,
changing field semantics, or changing canonicalization requires an explicit schema
version; golden-set content changes require a new golden-set version.

Rejected alternatives:

- Option 1 violates ADR-0010 C1, introduces credential and provider coupling, and makes
  default-off behavior harder to prove.
- Option 3 is reversible but does not leave a compatibility contract or auditable result
  format for the paid runs and downstream activation slices.
- Option 4 adds an operational dependency and a second scheduler without improving the
  deterministic structural grading required by this pilot.

### Consequences

- Positive: evaluation evidence is provider-independent, offline, deterministic, and
  reusable by later human-gated policy decisions. Unsafe and incomplete inputs fail
  before an eligibility claim can be produced.
- Positive: host invocation remains replaceable; the scorer consumes only a versioned
  data contract and does not depend on a provider or host SDK.
- Negative: the harness cannot launch, cancel, cryptographically attest, or contain a
  host execution. It relies on reported host/model identity and host-supplied containment
  evidence, which must be reviewed as directional rather than trusted telemetry.
- Negative: structural grading does not judge semantic quality, and maintaining schema
  compatibility adds work when the golden set or telemetry contract evolves.
- Neutral: #370 and #371 must make separate, evidence-backed activation decisions.
  This ADR neither narrows tools nor activates routing, merge, release, or Done.
- Follow-ups: paid pilot runs may broaden the golden set after human review; semantic or
  attested judging would require a separate ADR rather than widening this boundary.

## More information

- Contract: GitHub issue #369 and `docs/specs/369-behavioral-subagent-evals.md`.
- Related decisions: ADR-0010, ADR-0024, and ADR-0038. This record does not supersede
  them.
- Implementation branch: `feature/behavioral-subagent-evals`.
- This decision is also recorded in project memory via `save_decision`.
