# Design Contracts as Component Boundaries

Specify every component boundary as an enforceable contract — preconditions, postconditions, invariants, and a closed error set, all in domain terms — so a boundary can be implemented, replaced, and tested against its agreement rather than against any one implementation.

This is the role's primary output. A design contract is the agreement at a boundary, independent of what sits behind it.

## Design by Contract

The model is Meyer's Design by Contract (Eiffel): a software boundary is a contract between a caller (client) and an implementer (supplier).

- Preconditions — what the caller must guarantee before the call (validated inputs, required state, an auth context). A broken precondition is the caller's bug.
- Postconditions — what the supplier guarantees on successful return. A broken postcondition is the supplier's bug.
- Invariants — what stays true before and after every call on the component.

This splits blame cleanly: with explicit pre/postconditions you know which side failed without a debugger. It also defines substitutability — a replacement implementation may weaken preconditions and strengthen postconditions but never the reverse, which is exactly Liskov substitution (`solid_and_structural_discipline`). A contract is what makes a port swappable.

## The boundary checklist

For each boundary specify:

- Interface signature — operations, typed inputs and outputs, and the error/exception set. No internal types leak across the boundary.
- Preconditions, postconditions, invariants — as above.
- Error contract — the closed set of failure modes and how each is signaled. Callers must be able to enumerate what can go wrong.
- Idempotency and side effects — whether the operation is safe to retry, and what state mutates.
- Quality-of-service terms — latency budget, throughput cap, payload size limit, rate limits, consistency guarantee (strong versus eventual), and the versioning/compatibility policy.

## Contracts as the Ports and Adapters boundary

Align with the project default (`architecture_styles`): the Core Domain depends only on Ports expressed in domain primitives and domain models. Driving adapters call Incoming Ports; driven adapters implement Outgoing Ports. No transport- or database-specific type appears in a Port. Changing the database, swapping REST for gRPC, or replacing a broker must require only a new adapter with zero Core Domain edits. A contract that mentions `HttpRequest`, an ORM entity, or a JSON field name is leaking and must be rewritten in domain terms.

### Worked port and contract

```python
from typing import Protocol

class PaymentGateway(Protocol):
    """Outgoing port. Domain types only; no HTTP/SDK types cross this line.

    Preconditions:
      - amount.currency is supported and amount.value > 0
      - idempotency_key is unique per logical charge
    Postconditions (on success):
      - exactly one charge exists for idempotency_key (safe to retry)
      - returns a Receipt with a non-empty provider_ref
    Invariants:
      - never charges more than amount.value
    Errors (closed set):
      - InsufficientFunds, CardDeclined, GatewayTimeout
    QoS:
      - p99 < 800 ms; idempotent on idempotency_key; at-least-once retry safe
    """
    def charge(self, amount: Money, idempotency_key: str) -> Receipt: ...
```

The idempotency key in the precondition is what makes the at-least-once retry in the QoS line safe; the contract terms reinforce each other rather than standing alone.

## Schema-as-contract and consumer-driven contracts

A prose contract a reviewer reads is weaker than one a machine checks. Encode contracts in machine-checkable form:

- HTTP — OpenAPI 3.1 + JSON Schema; validate requests and responses against it in CI (see `rest_api_design`).
- gRPC — Protobuf `.proto` as the wire contract; backward compatibility enforced with `buf breaking`.
- Events — AsyncAPI for message schemas, backed by a schema registry with a compatibility mode (backward / forward / full).

Then add consumer-driven contract tests (Pact) so producer and consumer cannot drift silently: the consumer records its expectations, the provider verifies them in CI, and `can-i-deploy` blocks a release that would break a live consumer. A contract no test exercises is a comment, not a contract.

## Common pitfalls

- A contract written in transport or DB types (`HttpRequest`, an ORM row, a JSON field), which couples the Core Domain to a transport or store; a reviewer rejects it because swapping the adapter would now touch business rules.
- An open or undocumented error set, so callers cannot enumerate failures and write defensive handling; the failure modes must be a closed, named set.
- Chatty interfaces that force N round-trips for one use case, which couple the boundary to a calling pattern and wreck latency budgets.
- Boundaries that share mutable state instead of passing data, so the contract is implicit and untestable.
- "Just add a field" changes with no stated compatibility policy, which break consumers silently; every contract needs a versioning policy.
- Treating a database table as the integration contract between services, which leaks the schema and removes the ability to evolve either side.
- A prose-only contract with no schema or CDC test, so producer and consumer drift between releases.

## Definition of done

- [ ] Every boundary states preconditions, postconditions, invariants, a closed error set, idempotency/side-effects, and QoS terms.
- [ ] All types crossing the boundary are domain types; no transport- or DB-specific type leaks into a Port.
- [ ] Substitutability holds: an alternate implementation may weaken preconditions and strengthen postconditions only (Liskov).
- [ ] The contract is encoded in a machine-checkable schema (OpenAPI / Protobuf / AsyncAPI) wherever a wire format exists.
- [ ] Cross-service boundaries carry consumer-driven contract tests that gate deploys (Pact can-i-deploy).
- [ ] A versioning/compatibility policy is stated; changing the database or transport requires only a new adapter.
