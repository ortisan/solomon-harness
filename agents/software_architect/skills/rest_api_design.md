# REST API Design

Design an HTTP API as a contract over resources, not a transport for remote procedure calls, and decide its maturity level deliberately using the Richardson Maturity Model rather than drifting into it. This skill governs the architectural choices an HTTP API embodies: resource and URI modeling, method semantics, status-code selection, versioning, error format, caching, and the OpenAPI contract that precedes the code. It does not cover how the handlers are written or framework wiring; cross-reference the `software_engineer` skill for implementation, validation, and serialization mechanics.

## Richardson Maturity Model: pick a level on purpose

Martin Fowler's gloss on Leonard Richardson's model defines four levels. Treat them as a design target, not a grading curve.

- Level 0 — one URI, one verb (usually `POST`), the action carried in the body. This is RPC-over-HTTP, the "swamp of POX" (SOAP, XML-RPC, most "JSON endpoints" named `/api` with `{"action": "..."}`). HTTP is a tunnel; intermediaries see nothing useful.
- Level 1 — resources. Many URIs (`/orders/42`, `/customers/7`), but still one verb. You have nouns but no uniform method semantics.
- Level 2 — HTTP verbs and status codes. `GET`/`POST`/`PUT`/`PATCH`/`DELETE` carry meaning, status codes report outcome, safety and idempotency are honored. Caches, proxies, and clients can reason about requests. This is the pragmatic baseline for the overwhelming majority of public and internal JSON APIs in 2026; ship at least here.
- Level 3 — hypermedia controls (HATEOAS). Responses carry links and forms describing available next transitions, so clients are driven by the server's state machine rather than hardcoded URLs. Fowler calls this "the glory of REST." It pays off for long-lived APIs with many clients and evolving workflows (and is mandatory for true Roy Fielding REST). It is often over-engineering for a single first-party SPA or mobile client you ship in lockstep. State which level you target in the ADR and why.

A response that earns Level 3, using `application/hal+json` (RFC draft, widely deployed) or JSON:API (1.1):

```json
{
  "id": "42",
  "status": "awaiting_payment",
  "total": "59.90",
  "_links": {
    "self":   { "href": "/orders/42" },
    "pay":    { "href": "/orders/42/payment", "type": "application/json" },
    "cancel": { "href": "/orders/42", "method": "DELETE" }
  }
}
```

The `cancel` link only appears while cancellation is legal. Clients check for the link, not for `status == "awaiting_payment"`, which decouples them from your business rules.

## Resource and URI modeling

- Model nouns (resources), not verbs (actions). `POST /orders` not `POST /createOrder`. The verb is the HTTP method.
- Collections are plural, lowercase, kebab-case: `/purchase-orders`, `/users/{id}/payment-methods`. Pick singular-vs-plural once and never mix.
- Identify resources with stable, opaque IDs (UUIDv7 for new designs — time-ordered, index-friendly; cross-reference `software_engineer`). Never put database surrogate keys in URLs if they leak ordering or counts you would rather not expose.
- Nest only to express containment, and stop at one level: `/orders/42/lines/9`. Deeper nesting (`/customers/7/orders/42/lines/9/discounts`) couples clients to a tree; expose `/lines/9` directly and link.
- Some operations are genuinely not CRUD on a resource (search, batch, state transitions). Model them as a sub-resource or a controller resource: `POST /orders/42/cancellation`, `POST /transfers`. Do not smuggle an RPC verb back into the path as `/orders/42/cancel` unless the team has agreed to that controller convention.

## HTTP methods: safety and idempotency are contracts

Safety (no observable state change) and idempotency (N identical calls have the same effect as one) are guarantees clients, proxies, and retry logic depend on. Violating them silently breaks every layer above you.

| Method | Safe | Idempotent | Use |
|--------|------|-----------|-----|
| GET    | yes  | yes        | Read. Never mutate, ever. A `GET` with side effects breaks prefetch and caches. |
| HEAD   | yes  | yes        | Headers/existence only. |
| PUT    | no   | yes        | Full replace at a known URI. Send the complete representation. |
| PATCH  | no   | no*        | Partial update. Use JSON Merge Patch (RFC 7396) for simple fields or JSON Patch (RFC 6902) for precise ops. |
| POST   | no   | no         | Create in a collection, or non-idempotent action. |
| DELETE | no   | yes        | Remove. Second `DELETE` returns `404` or `204`; either is idempotent in effect. |

\* `PATCH` is not inherently idempotent; a Merge Patch that sets absolute values usually is, a JSON Patch with `add` to an array is not. Document which yours is. For non-idempotent `POST`/`PATCH`, support idempotency keys (below). Per RFC 9110, an origin server should reject a `PATCH` whose body it cannot apply atomically rather than partially apply it.

## Status codes that mean something

Select the most specific code; clients branch on the class (2xx/4xx/5xx) and then the exact code.

- `200` read/update with body, `201 Created` with a `Location` header to the new resource, `202 Accepted` for async work (return a status resource to poll), `204 No Content` for a successful write with no body.
- `400` malformed/invalid input, `401` unauthenticated, `403` authenticated but forbidden, `404` not found (also for hiding existence from unauthorized callers), `409 Conflict` for optimistic-concurrency or state conflicts, `410 Gone` for removed resources, `422` for syntactically valid but semantically rejected payloads (only if your contract distinguishes it from `400` — pick one convention), `429` rate limited with `Retry-After`.
- `412 Precondition Failed` when an `If-Match`/`If-Unmodified-Since` guard fails; `428 Precondition Required` to force conditional writes.
- `5xx` is your fault: `500` unexpected, `502`/`503`/`504` for upstream/availability. Never return `200` with an `{"error": ...}` body; that is Level 0 thinking and defeats every generic client and monitor.

## Error bodies: RFC 9457 problem+json

Standardize every error on RFC 9457 (Problem Details for HTTP APIs, which obsoletes RFC 7807). Media type `application/problem+json`. This is non-negotiable for a coherent API surface.

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/insufficient-funds",
  "title": "Insufficient funds",
  "status": 409,
  "detail": "Account 7 balance 12.00 is below the 59.90 charge.",
  "instance": "/accounts/7/charges/abf3",
  "balance": "12.00",
  "required": "59.90"
}
```

`type` is a stable URI (a documentation page is fine) clients switch on; `title` is human-stable; `detail` is instance-specific; `instance` identifies this occurrence. Extension members (`balance`, `required`) carry machine-readable specifics. Define your `type` catalog as part of the contract so error handling is data, not scattered string matching.

## Content negotiation and versioning

- Negotiate representation with `Accept`/`Content-Type`. Default to `application/json`; reserve vendor media types (`application/vnd.example.order.v2+json`) for media-type versioning if you choose it.
- Choose one versioning strategy and apply it uniformly. URI versioning (`/v2/orders`) is the most operable: visible, cacheable, trivial to route, and easy for clients to reason about — recommended default for public APIs. Header versioning (`Api-Version: 2026-01-15`, date-based) keeps URLs clean and suits fast-moving internal APIs. Media-type versioning is the most RESTful and the least convenient; reserve it for hypermedia APIs that already negotiate. Document the deprecation path with the `Deprecation` and `Sunset` (RFC 8594) headers and a timeline.
- Version the contract, not every field. Add optional fields and new endpoints without a version bump (additive changes are backward compatible). Bump only on breaking changes: removing/renaming fields, changing types, tightening validation, changing semantics.

## Pagination, filtering, sorting

- Prefer cursor (keyset) pagination for large or live collections: `GET /orders?limit=50&cursor=eyJpZCI6NDJ9`. It is stable under inserts and has bounded cost, unlike `offset`/`page`, which drifts and degrades on deep pages. Return the next cursor in the body and/or `Link` headers (RFC 8288): `Link: </orders?cursor=...>; rel="next"`.
- Cap and default `limit` (e.g. default 25, max 100) so a client cannot demand an unbounded page.
- Filtering and sorting are query parameters: `?status=open&sort=-created_at`. Define the exact allowed filter fields and operators in the contract; do not accept arbitrary query DSLs that expose the data model or enable expensive scans.

## Caching, ETags, and conditional requests

- Make `GET`s cacheable. Send `Cache-Control` (`max-age`, `private`/`public`, `no-store` for sensitive data) and an `ETag` (strong validator, typically a hash or version of the representation).
- Support conditional reads: client sends `If-None-Match: "v7"`, server returns `304 Not Modified` with no body when unchanged. This cuts bandwidth and is the cheapest performance win an API has.
- Support conditional writes for optimistic concurrency: require `If-Match: "v7"` on `PUT`/`PATCH`/`DELETE`, return `412 Precondition Failed` on mismatch. This is how you prevent lost updates without server-side locks, and it is an architectural decision, not an implementation detail.

## Idempotency keys for unsafe writes

Non-idempotent `POST` (payments, order creation) needs a client-supplied idempotency key so retries after a timeout do not double-charge. This is now an IETF draft (`Idempotency-Key` header) and the de-facto pattern Stripe popularized.

```http
POST /charges
Idempotency-Key: 6f3a-...-c1
Content-Type: application/json
```

The server stores the key with the first response, scoped to the endpoint and caller, for a documented retention window (24h is typical). A repeat with the same key replays the stored response; the same key with a different body is a `422`. Specify retention, scope, and conflict behavior in the contract.

## Contract-first with OpenAPI 3.1

Author the OpenAPI 3.1 document before the implementation. OpenAPI 3.1 is fully JSON Schema 2020-12 compatible, so request/response schemas double as validation schemas. The contract is the design artifact this role owns; it is reviewed, versioned, and is the source of truth from which servers, clients, and mock servers are generated (cross-reference `software_engineer` for codegen and test wiring).

```yaml
openapi: 3.1.0
info: { title: Orders API, version: "2.3.0" }
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - { name: id, in: path, required: true, schema: { type: string, format: uuid } }
      responses:
        "200":
          headers: { ETag: { schema: { type: string } } }
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Order" }
        "404":
          content:
            application/problem+json:
              schema: { $ref: "#/components/schemas/Problem" }
```

Lint the spec in CI (Spectral with a ruleset enforcing naming, problem+json on errors, and security on every operation), and run contract tests (Schemathesis, or Pact for consumer-driven contracts) so the implementation cannot drift from the document.

## When REST is the right choice

REST over HTTP/JSON is the default for resource-oriented, cacheable, broadly-consumed APIs (public APIs, CRUD-heavy services, anything fronted by CDNs and browsers). Reach for an alternative when the shape of the problem fights REST:

- gRPC (HTTP/2, Protobuf) for low-latency, high-throughput internal service-to-service calls and streaming, where a tight schema and binary framing beat human-readability and cacheability. Poor fit for browsers and public consumption.
- GraphQL when clients need to compose highly variable views over a deep graph and you want to eliminate over/under-fetching across many screens, accepting the cost of caching, rate-limiting, and query-complexity control moving into your layer.
- Event-driven / async messaging (Kafka, AMQP, webhooks, AsyncAPI for the contract) when the interaction is notification or fire-and-forget, not request/response, or when you need decoupling and replay. Document these with AsyncAPI, not OpenAPI.

Record the choice in an ADR with the forces that drove it; "we used REST because it is familiar" is not a recorded decision.

## Common pitfalls

- Level 0 in disguise: a single `POST /api` (or `/graphql`-shaped JSON-RPC) with an action field, then calling it REST. Reject; it forfeits every HTTP affordance.
- `GET` with side effects, or tunneling writes through `GET` to avoid CORS/preflight. Breaks caches, prefetch, and retries.
- `200 OK` wrapping an error envelope. Monitors, proxies, and generic clients cannot tell success from failure. Use the right status and problem+json.
- Verb-in-URI design (`/getUser`, `/orders/42/cancel`) without an agreed controller convention; it abandons uniform method semantics.
- Offset pagination on a large, mutating collection: duplicates/skips under concurrent writes and O(n) deep-page cost. Use cursors.
- Breaking changes shipped without a version bump or `Deprecation`/`Sunset` headers, silently breaking live clients.
- Ad hoc per-endpoint error JSON instead of RFC 9457, forcing clients to special-case each route.
- Non-idempotent `POST` for payments with no idempotency key, so a network retry double-charges.
- `PUT` used for partial update (it must replace the whole representation) or `PATCH` documented as idempotent when its body is not.
- Implementation-led design: handlers written first and the OpenAPI spec generated and patched afterward, so the contract is a description, not a design.

## Definition of done

- [ ] The targeted Richardson level is stated in an ADR with justification; if below Level 3, the reason hypermedia was not needed is recorded.
- [ ] Resources are nouns with stable opaque IDs, consistent plural kebab-case URIs, and nesting no deeper than one containment level.
- [ ] Every method honors its safety and idempotency contract; `GET` is side-effect-free; `PUT` replaces, `PATCH` is documented as Merge or JSON Patch and as idempotent or not.
- [ ] Status codes are specific and correct; no `200` error envelopes; `201` carries `Location`, `202` returns a pollable status resource.
- [ ] All errors use RFC 9457 `application/problem+json` with a documented `type` catalog.
- [ ] One versioning strategy is applied uniformly, additive changes do not bump the version, and breaking changes ship with `Deprecation`/`Sunset` and a timeline.
- [ ] Collections use cursor pagination with capped `limit`, declared filter/sort fields, and `Link` rel="next".
- [ ] `GET`s send `ETag`/`Cache-Control` and honor `If-None-Match`; mutations support `If-Match` optimistic concurrency returning `412`.
- [ ] Non-idempotent writes accept an `Idempotency-Key` with documented scope, retention, and conflict behavior.
- [ ] An OpenAPI 3.1 contract exists, is version-controlled, lints clean in CI (Spectral), and is covered by contract tests; it was authored before the implementation.
- [ ] An ADR records why REST was chosen over gRPC, GraphQL, or event-driven for this boundary.
