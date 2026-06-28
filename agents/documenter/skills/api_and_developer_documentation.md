## API and developer documentation


- Reference is generated from a machine-readable contract, not hand-written. Maintain an OpenAPI 3.1 spec (or AsyncAPI for event APIs) as the source of truth; render with Redoc, Swagger UI, or Stoplight Elements. Lint the spec with Spectral in CI.
- Every endpoint documents: purpose, auth/scopes required, all parameters with types and constraints, request body schema, every response status with body schema, error codes with causes and fixes, rate limits, idempotency, and pagination.
- Provide at least one complete request/response example per endpoint, including a failure example. Examples must match the current schema; validate them against the spec.
- Document authentication end to end once (obtaining credentials, sending them, refreshing, scopes) and link endpoints to it.
- Provide a quickstart that gets a developer to a first successful call in under 15 minutes, and SDK snippets in the languages your users actually use.
- Version the API docs with the API. Keep a changelog and a deprecation policy that states timelines and migration steps. Signal pending removal on the wire with the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) response headers and document the dates; never silently remove an endpoint from the reference.
