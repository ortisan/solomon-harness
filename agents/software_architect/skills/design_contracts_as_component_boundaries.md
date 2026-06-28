## Design contracts as component boundaries


This is the role's primary output. A design contract is the enforceable agreement at a component boundary, independent of implementation.

For each boundary specify:

- **Interface signature** — operations, typed inputs and outputs, error/exception set. No leaking of internal types across the boundary.
- **Preconditions** — what the caller must guarantee (validated inputs, required state, auth context).
- **Postconditions** — what the component guarantees on success.
- **Invariants** — what stays true before and after every call.
- **Error contract** — the closed set of failure modes and how each is signaled. Callers must be able to enumerate what can go wrong.
- **Idempotency and side effects** — is the operation safe to retry; what state mutates.
- **Quality-of-service terms** — latency budget, throughput limit, payload size cap, rate limits, consistency guarantee (strong vs eventual), versioning/compatibility policy.

Align with the project's Hexagonal Architecture: the Core Domain depends only on Ports expressed in domain primitives and domain models. Driving (input) adapters call Incoming Ports; Driven (output) adapters implement Outgoing Ports. No transport-specific or database-specific types appear in a Port. Changing database, swapping REST for gRPC, or replacing a broker must require only a new adapter, with zero Core Domain edits. A contract that mentions `HttpRequest`, an ORM entity, or a JSON field is leaking and must be rewritten in domain terms.

Encode contracts in machine-checkable form wherever possible: OpenAPI/JSON Schema for HTTP, Protobuf/`.proto` for gRPC, AsyncAPI for events, plus consumer-driven contract tests (Pact-style) so producer and consumer cannot drift silently. A contract no test exercises is a comment.

Pitfalls: chatty interfaces that force N calls for one use case; boundaries that share mutable state instead of passing data; "just add a field" changes that break consumers because no compatibility policy was stated; treating a database table as an integration contract between services.
