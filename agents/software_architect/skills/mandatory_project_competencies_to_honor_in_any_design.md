---
name: mandatory-project-competencies-to-honor-in-any-design
description: Governs translating testability seams, consumer-driven contract test isolation, a per-container STRIDE table, and ML and quant safety guards such as leakage-free splits, tensor shape checks, and Sharpe, drawdown, and profit-factor thresholds into structural design decisions rather than review-time fixes. Use when designing a boundary that must be unit-testable, security-reviewed, or backed by an ML or quant strategy contract.
---

# Honoring Project Competencies at Design Time

Translate the project's non-negotiable competencies — testability, test isolation, security, and the ML and quant safety guards — into structural decisions made while designing, so compliance is built into the boundaries instead of bolted on at review.

The shared rules in `agents/AGENTS.md` state what is required; this skill is about where each requirement lands in a design. Enforcement at the checkpoint is the `architecture_review_gate`; the techniques to design these in are below.

## Testability as a structural property

TDD is only cheap if the architecture lets a unit test run without infrastructure. Design the seams:

- Inject every ambient dependency at a boundary: the clock, randomness, the network, the filesystem, environment. A use case that calls `datetime.now()` or `requests.get()` directly cannot be tested deterministically; pass a `Clock` and a port instead.
- Keep the Core Domain free of I/O so it is pure-function testable (`architecture_styles`, the functional core / imperative shell pattern). Tests of policy then need no mocks at all.
- Apply the humble-object pattern at adapters: push logic out of the hard-to-test edge (the controller, the DB driver) into a plain object the test can exercise directly.

The seam is the same Port the design contract defines (`design_contracts_as_component_boundaries`); designing for testability and designing the contract are one act.

## Test isolation: name what gets mocked, and contract it

Tests must mock external services to stay deterministic, so the design must make every external call a substitutable port and must state which doubles replace it. For service-to-service boundaries, specify consumer-driven contract (CDC) tests so a mock cannot drift from the real provider:

- The consumer writes its expectation against the provider's port; Pact records it as a pact file in the broker.
- The provider verifies every recorded pact in its own CI; `pact-broker can-i-deploy` blocks a release that would break a live consumer.
- This catches the failure unit-level mocks hide: the mock and the real provider disagreeing.

Cross-reference `rest_api_design` for HTTP-contract specifics; the design's job is to declare that each cross-service boundary carries a CDC test.

## Security: a worked STRIDE-per-container pass

Run STRIDE against every Container and trust-boundary crossing at design time, and record the mitigation as a design decision. The deep walk and the severity rubric live in `architecture_review_gate` and the `security` agent; the architect produces the table that makes the boundary explicit.

| Container / boundary | Threat (STRIDE) | Mitigation in the design |
|---|---|---|
| Public API gateway | Spoofing | OIDC bearer tokens, validated at the edge |
| API -> orders service | Tampering | mTLS in the mesh; input validation at the port |
| Orders service | Repudiation | Append-only audit log with actor + timestamp |
| Orders DB | Information disclosure | AES-256 at rest, KMS keys, least-privilege role |
| Public API gateway | Denial of service | Rate limit per principal, timeouts, bulkhead (`resilience_patterns`) |
| Admin endpoints | Elevation of privilege | Server-side authz on every call, never client-trusted |

An unmitigated high-severity threat at a boundary handling regulated or high-value data blocks the design.

## ML/DRL and quant guards as contract terms

Where the system trains models or trades, the project's safety rules become preconditions, postconditions, and fitness functions, not prose:

- Data leakage — design strict train/validation/test and walk-forward splits into the pipeline so future information cannot reach a feature by construction; make "no overlap between train and test windows" a checked invariant, not a convention.
- Numerical guards — put shape validation and division-by-zero / overflow guards as preconditions on the contract of every critical tensor op, so a malformed tensor fails at the boundary, not three layers in.
- Quant hypothesis — an architecture that supports a strategy must carry the hypothesis as asserted thresholds: target Sharpe (for example >= 1.5 net of costs), max drawdown (for example <= 20%), min profit factor (for example >= 1.3), and the latency/slippage budget (for example sub-50 ms decision-to-order, slippage modeled per instrument). No backtest path is valid without realistic transaction costs and slippage modeled in.

These belong to the `ml_engineer` and `quant_trader` agents to implement; the architect's job is to give them a boundary where the guard is mandatory and verifiable.

## Common pitfalls

- A use case that reads the clock, randomness, or network directly, which makes deterministic unit tests impossible; a reviewer rejects it because TDD cannot hold.
- Mocking a provider in consumer tests with no CDC contract, so the mock and the real provider drift and integration breaks in production despite green unit suites.
- A STRIDE "pass" that is a checkbox rather than a per-container table, so a trust boundary ships unmitigated; the gate rejects an unwalked boundary.
- ML splits enforced by convention instead of by construction, allowing leakage that inflates backtest metrics; design the split as a checked invariant.
- A backtest path with no transaction-cost or slippage model, which produces results that cannot be trusted and a reviewer rejects outright.
- Restating the project rules in a design doc instead of placing each as a seam, contract term, or fitness function, which is documentation without enforcement.

## Definition of done

- [ ] Every ambient dependency (clock, randomness, I/O, env) is injected at a boundary; the Core Domain is unit-testable without infrastructure.
- [ ] Each cross-service boundary names its test doubles and carries a consumer-driven contract test that gates deploys.
- [ ] A STRIDE-per-container table exists; no unmitigated high-severity threat remains at a regulated or high-value boundary.
- [ ] ML pipelines design leakage-free splits as checked invariants; critical tensor ops carry shape and numerical guards as preconditions.
- [ ] Any supported quant strategy carries Sharpe, drawdown, profit-factor, and latency/slippage thresholds, with costs and slippage modeled.
- [ ] Each competency is realized as a seam, contract term, or fitness function, and handed to the `architecture_review_gate` to enforce.
