# REST API Implementation

Make the HTTP layer carry the contract: the status code states the outcome, the method's safety and idempotency promises are actually enforced, and every error body, page, and validation rule is generated from the same code that enforces it rather than hand-written prose that drifts. This skill is implementation in code; the architectural framing (resources, hypermedia, the Richardson Maturity Model levels) belongs to the `software_architect` `rest_api_design` skill, and request-boundary validation extends the `robust_defensive_code` skill. Examples target this project's stack: FastAPI 0.115+ on Starlette with Pydantic 2.x (2.11+), which emits OpenAPI 3.1 directly.

## Status codes map to outcomes, not to vibes

Pick the code from what happened to the resource, per RFC 9110 (HTTP Semantics, 2022). The body is detail; the status line is the API.

- `200 OK` — read or update returning a representation. `201 Created` — a new resource exists; set `Location` to its URI. `202 Accepted` — work queued, not done; return a status URL. `204 No Content` — success with empty body (a `DELETE`, or a `PUT` you do not echo).
- `400` malformed syntax; `401` missing/invalid credentials (with `WWW-Authenticate`); `403` authenticated but not allowed; `404` absent or hidden-for-authz; `405` wrong method (must send `Allow`); `409` state conflict (duplicate, version clash); `410` gone permanently; `415` unsupported request media type; `422` syntactically valid but semantically rejected; `428` precondition required; `429` rate limited (with `Retry-After`).
- `5xx` is "we failed," never "you sent bad input." A validation failure is `4xx`. Returning `500` for a bad request hides client bugs and pollutes error budgets that the `sre` and `observability` agents track.

```python
from fastapi import FastAPI, Response, status

app = FastAPI()

@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderIn, response: Response) -> OrderOut:
    order = orders.create(body)
    response.headers["Location"] = f"/orders/{order.id}"
    return OrderOut.model_validate(order)
```

## Method semantics: safe and idempotent are guarantees, not labels

`GET`, `HEAD`, `OPTIONS` are safe (no observable state change) and must stay that way — no side effects, so caches and prefetchers can replay them freely. `PUT` and `DELETE` are idempotent: calling them N times leaves the same end state as once. `POST` and `PATCH` are neither safe nor idempotent in general. Implement to the guarantee: a `DELETE` on an already-deleted resource returns `204` (or `404`), not an error; a `PUT` writes the full target state so a retry overwrites identically. Never hide a mutation behind `GET` because it was convenient for a browser link.

## Idempotency keys for non-idempotent POSTs

Money movement, order creation, and any POST a client may retry needs an `Idempotency-Key` (the Stripe convention, formalized in `draft-ietf-httpapi-idempotency-key-header`). The client sends a unique key per logical operation; the server replays the original response on a repeat instead of acting twice.

```python
async def idempotent(request: Request) -> Response | None:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise problem(422, "Idempotency-Key header required")
    fingerprint = sha256(await request.body()).hexdigest()
    row = await store.get(key)            # row = (fingerprint, status, body) or None
    if row and row.fingerprint != fingerprint:
        raise problem(409, "Idempotency-Key reused with a different request body")
    if row and row.completed:
        return Response(row.body, row.status, media_type="application/json")
    if row and not row.completed:
        raise problem(409, "A request with this Idempotency-Key is in progress")
    await store.reserve(key, fingerprint)  # atomic insert; the unique constraint is the lock
    return None                            # proceed, then store.complete(key, response)
```

- The unique constraint on the key column is the concurrency lock; rely on it instead of an application mutex. Store the response body and status so a replay is byte-identical.
- Bind the key to a request fingerprint and return `409` if the same key arrives with a different body — that is a client bug, not a replay.
- Set a retention TTL (24 hours is the common floor) and document it. Keys are per endpoint and per account, not global.

## Conditional requests: ETag, If-Match, If-None-Match

Conditional requests (RFC 9110 §8.8, §13) give you cheap caching and optimistic concurrency with no extra round trip. Return an `ETag` on representations; let clients revalidate and write safely.

```python
@app.get("/orders/{oid}")
def get_order(oid: str, request: Request, response: Response):
    order = orders.get_or_404(oid)
    etag = f'"{order.version}"'                      # strong validator from a row version
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304)             # client cache is fresh, no body
    response.headers["ETag"] = etag
    return OrderOut.model_validate(order)

@app.put("/orders/{oid}")
def replace_order(oid: str, body: OrderIn, request: Request):
    inm = request.headers.get("If-Match")
    if inm is None:
        raise problem(428, "If-Match required to update this resource")  # Precondition Required
    if inm != f'"{orders.version_of(oid)}"':
        raise problem(412, "Resource was modified; re-fetch and retry")  # Precondition Failed
    return orders.replace(oid, body)
```

- `If-None-Match` on reads yields `304 Not Modified` (empty body) when the cached copy is current — this is the bandwidth win.
- `If-Match` on writes yields `412 Precondition Failed` on a stale write, which is how you stop lost updates without table locks. Require it with `428` on resources where concurrent edits are realistic.
- Use strong validators (a row version or content hash). Weak ETags (`W/"..."`) only assert semantic equivalence and must not gate `If-Match` writes.

## Pagination: cursor by default, offset only when bounded

Offset pagination (`?limit=20&offset=10000`) makes the database scan and discard every skipped row, so deep pages degrade to O(n) and items shift when rows are inserted mid-scan. Use keyset (cursor) pagination for any list that grows or is sorted by time.

```python
@app.get("/orders")
def list_orders(limit: int = Query(20, le=100), cursor: str | None = None):
    after = decode_cursor(cursor)                    # base64 of (created_at, id) tiebreaker
    rows = orders.page(after=after, limit=limit + 1) # fetch one extra to detect "more"
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1]) if has_more else None
    return {"items": [OrderOut.model_validate(r) for r in rows], "next_cursor": next_cursor}
```

- The cursor is opaque base64 over the sort key plus a unique tiebreaker (`id`); never expose a raw offset or primary key the client can tamper with. Cap `limit` (100 here) so a caller cannot request the whole table.
- The WHERE clause must use the same composite ordering as the cursor (`(created_at, id) > (?, ?)`) or you skip or repeat rows at page boundaries.
- Offset is acceptable only for small, fixed result sets where users need page numbers (an admin table of dozens of rows). Document which endpoints offer which.

## Error bodies: RFC 9457 problem+json

Return machine-readable errors with `Content-Type: application/problem+json` per RFC 9457 (2023, obsoletes RFC 7807). One shape across the API beats per-endpoint ad-hoc JSON. Required-ish members: `type` (a URI, `about:blank` if none), `title`, `status`; useful: `detail`, `instance`, plus domain extensions.

```python
from fastapi.responses import JSONResponse

def problem(status: int, detail: str, *, type_="about:blank", **ext) -> HTTPException:
    return HTTPException(status, {"type": type_, "title": HTTPStatus(status).phrase,
                                  "status": status, "detail": detail, **ext})

@app.exception_handler(HTTPException)
async def problem_handler(_: Request, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"title": str(exc.detail)}
    return JSONResponse(body, status_code=exc.status_code,
                        media_type="application/problem+json")
```

- Keep `detail` safe for external eyes: no stack traces, SQL, or internal hostnames (see `robust_defensive_code`). Put the correlation/trace id in an extension member so support can find the server-side log.
- Use a stable `type` URI per error class so clients branch on `type`, not on prose in `title`. The `instance` is the occurrence; `type` is the category.

## Content negotiation and request media types

Honor `Accept` for response format and validate `Content-Type` for the request. Reject an unsupported request body with `415`; reject an unserveable `Accept` with `406`. Set `Vary: Accept` on any response whose body depends on negotiation so shared caches do not serve the wrong representation. Do not silently ignore `Accept` and always return JSON — either serve what was asked or return `406`. Use language negotiation (`Accept-Language`) for localized error `detail` only if you actually localize.

## Request validation at the boundary

Validate every inbound payload against a strict schema before the domain sees it; this is the HTTP face of `robust_defensive_code`. With Pydantic 2.x, declare request models with `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected rather than dropped, constrain types (`Annotated[int, Field(ge=1, le=100)]`, `EmailStr`), and let FastAPI reject violations. FastAPI's default is `422` with a per-field error array; wrap it so the body is problem+json:

```python
@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        {"type": "https://errors.example.com/validation", "title": "Invalid request",
         "status": 422, "errors": exc.errors()},
        status_code=422, media_type="application/problem+json")
```

Validate at the edge only; do not re-parse raw dicts deeper in the call stack. The validated model is the contract the rest of the code trusts.

## OpenAPI 3.1 generated from code

The schema must come from the handlers, not a separate hand-edited file that lies. FastAPI serves OpenAPI 3.1 at `/openapi.json` derived from the Pydantic models and signatures. Make it complete and gate it in CI.

- Declare every non-default response so the spec lists `409`, `412`, `422`, etc.: `@app.post(..., responses={409: {"model": Problem}, 422: {"model": Problem}})`. An undocumented status code is a broken contract for SDK generators.
- In CI, export the spec and diff it against the committed baseline with `oasdiff` to fail the build on undeclared breaking changes; lint with Spectral (Stoplight) for style; run Schemathesis 4.x property-based tests that fuzz every operation against its own schema to catch handlers that violate the contract they advertise.
- Generate client SDKs and mock servers from the same spec so consumers never reverse-engineer the API by reading source.

(DRF projects get the equivalent OpenAPI 3.1 output from drf-spectacular 0.27+; NestJS 11 from `@nestjs/swagger`. The rule is identical: the spec is generated, diffed, and tested, never authored by hand.)

## Versioning in practice

Version only when you must break a contract; additive changes (a new optional field, a new endpoint, a new enum value clients are told to tolerate) never bump a version. For a real break, prefer a major version in the URI path (`/v1/orders`) — it is unambiguous in logs, caches, and routing, even if it is less "pure" than media-type versioning (`Accept: application/vnd.example.v2+json`). Pick one scheme and apply it everywhere.

Run old and new majors side by side during migration. Signal retirement with the `Deprecation` response header (RFC 9745, 2024) and a hard date in `Sunset` (RFC 8594), plus a `Link` to migration docs:

```http
Deprecation: @1735689600
Sunset: Wed, 31 Dec 2025 23:59:59 GMT
Link: <https://docs.example.com/migrate/v2>; rel="deprecation"
```

Never repurpose an existing field's meaning or tighten validation inside a version — that is a silent break worse than a version bump, because clients get no signal.

## Common pitfalls

- `200 OK` with an error object in the body. The status line is the contract; an error must be `4xx`/`5xx` or every client must parse bodies to know if the call worked.
- `5xx` returned for client input errors, inflating the error budget and masking that the caller is broken. Validation failures are `4xx`.
- `POST` retried after a network timeout creating duplicate orders because there is no `Idempotency-Key` path. Any retryable mutation needs one.
- A mutating `GET` (e.g. `GET /jobs/123/run`). Caches and prefetchers will fire it; safety is a hard guarantee, not a suggestion.
- Offset pagination on a growing, time-sorted list: deep pages scan the whole table and rows shift between pages. Use keyset cursors.
- ETag generated from a timestamp with second precision or a non-deterministic dict ordering, so two identical representations get different tags and revalidation never hits `304`.
- `If-Match` accepted but never enforced, so concurrent `PUT`s silently lose updates. A stale precondition must return `412`.
- Per-endpoint bespoke error JSON instead of one `application/problem+json` shape, forcing every client to special-case each route.
- Pydantic models without `extra="forbid"`, so typo'd or injected fields pass silently and the handler operates on data it never validated.
- The committed OpenAPI file edited by hand and drifting from the handlers; or new status codes shipped without adding them to `responses=`, so generated SDKs cannot handle them.
- A breaking change shipped under the same version by redefining a field or tightening validation, with no `Deprecation`/`Sunset` signal.

## Definition of done

- [ ] Every endpoint returns the status code that matches the outcome (`201`+`Location` on create, `204` on empty success, `409`/`412`/`415`/`422`/`428`/`429` mapped deliberately); no `2xx`-with-error-body and no `5xx` for client input.
- [ ] Safe methods cause no state change; `PUT`/`DELETE` are idempotent; retryable `POST`/`PATCH` accept an `Idempotency-Key`, replay the stored response, and `409` on key reuse with a different body.
- [ ] Reads emit strong `ETag`s and honor `If-None-Match` with `304`; concurrent-edit writes require `If-Match`, returning `428` when absent and `412` when stale.
- [ ] List endpoints use capped keyset/cursor pagination by default; offset is used only for small bounded sets and is documented as such.
- [ ] All errors are `application/problem+json` (RFC 9457) with a stable `type`, no internal detail leaked, and a trace id for correlation.
- [ ] Requests are validated at the boundary with strict Pydantic models (`extra="forbid"`, typed constraints); `Content-Type`/`Accept` negotiated with `415`/`406` and `Vary: Accept`.
- [ ] OpenAPI 3.1 is generated from the code, declares every response status, and is diffed (`oasdiff`), linted (Spectral), and contract-tested (Schemathesis) in CI.
- [ ] Versioning is consistent (URI major version), additive changes do not bump it, and retirements ship `Deprecation` + `Sunset` + migration `Link`.
- [ ] Tests cover idempotency replay, `412`/`428` precondition paths, `304` revalidation, cursor page boundaries, and validation rejection, with external dependencies mocked per the `qa` standard.
