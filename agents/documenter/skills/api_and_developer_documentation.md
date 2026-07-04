# API and Developer Documentation

API reference is generated from a machine-readable contract; hand-written reference is a defect. This skill governs the OpenAPI discipline, the examples-first reference standard, quickstart quality measured as time-to-first-success, versioning and deprecation documentation, and the docs-as-code pipeline that keeps all of it honest in CI.

## The contract is the source of truth

- Maintain an OpenAPI 3.1 spec for HTTP APIs. 3.1 aligns with JSON Schema draft 2020-12, so the same schemas drive validators, mocks, and codegen without dialect conversion. Use AsyncAPI 3.0 for event-driven APIs.
- Design-first and code-first are both acceptable, but the spec is canonical either way. If annotations generate it, commit the generated spec and diff it in CI so every contract change is visible in review.
- Lint with Spectral in CI using a project ruleset stricter than the default `spectral:oas`: require `operationId`, `summary`, and `description` on every operation, a described schema for every response including errors, `tags` from a controlled list, and no orphan schemas. A spec that passes only the default ruleset can still render an empty page per endpoint.
- Render with Redoc, Swagger UI, or Stoplight Elements. The renderer is presentation only; never edit rendered output.

## Examples-first reference

Every endpoint documents purpose, auth and required scopes, all parameters with types and constraints, request and response schemas per status code, error causes and fixes, rate limits, idempotency behavior, and pagination. On top of the schema:

- Provide at least one complete, runnable success example per endpoint — request and response bodies with realistic values, not `<placeholder>` soup — and at least one failure example showing the error envelope.
- Keep examples in the spec (`examples` objects), not only in prose, and validate them against their schemas in CI (Spectral custom functions or `openapi-examples-validator`). Contract-test the live API against the spec with Schemathesis where feasible. An example that no longer validates is a build failure, not a doc nit.
- Document errors once, as a family: use RFC 9457 Problem Details (`application/problem+json`, which obsoletes RFC 7807), and list every `type` with its cause and the client's corrective action. Endpoint pages link the family instead of restating it.
- Document authentication end to end exactly once — obtaining credentials, sending them, refreshing, scopes — and link every endpoint to that page rather than repeating fragments that drift.

## Quickstart and time-to-first-success

The quickstart is measured, not admired. Its metric is time-to-first-success (TTFS): wall-clock time for a new developer, starting with zero credentials, to reach a first successful API call. Target under 15 minutes. Measure it with real newcomers or usability sessions and treat a regression like a performance regression.

- One linear path, no options: obtain a key, install one client, make one call, see one verifiable response. Alternatives belong in how-to guides.
- Count credential acquisition inside TTFS; signup friction is part of the developer's first experience whether or not the docs caused it.
- Provide copy-paste snippets in the languages your users actually use (check SDK download numbers, not aspirations), plus raw `curl`. Execute every snippet in CI against a sandbox; untested snippets rot within one release.

## Versioning, changelog, deprecation

- Version the docs with the API. A reader integrating against v2 must be able to pin v2 docs; "latest"-only documentation strands existing integrations on wrong instructions.
- Keep a per-version changelog written for API consumers — what changed on the wire and what to do about it — not a commit log.
- The deprecation policy states timelines and migration steps. Signal pending removal on the wire with the `Deprecation` header (RFC 9745) and the `Sunset` header (RFC 8594), mark the operation `deprecated: true` in the spec so renderers flag it, and print the same dates in the reference. Never silently remove an endpoint: keep its page through the sunset date with the migration link, then redirect.

## Docs-as-code pipeline

The spec, reference, and guides live in the repository and ship through pull requests like code. Minimum CI stages: Spectral lint; example and schema validation; snippet execution against a sandbox; link check (`lychee`); prose lint (Vale); and a per-PR preview deploy so reviewers read the rendered result, not raw diffs. Run breaking-change detection on the spec diff (`oasdiff` or equivalent) and post the result to the PR, so an incompatible contract change cannot merge unlabeled.

## Common pitfalls

- Hand-editing rendered reference pages, or describing endpoints in prose while the spec drifts; the spec and the docs must fail together or not at all.
- Examples invented in prose that no longer validate. A 400 on the copy-pasted example destroys trust in the entire reference.
- Quickstarts padded with concept teaching or configuration options; TTFS balloons and the one guaranteed path disappears.
- Authentication explained in per-endpoint fragments that contradict each other after the next auth change.
- Publishing only "latest" docs, so users on older API versions follow instructions that do not apply.
- Deprecations announced only in a blog post, with no `Deprecation`/`Sunset` headers and no `deprecated: true` flag; clients get no machine-readable warning.
- Relying on the default Spectral ruleset and calling the spec "linted" while operations lack descriptions and error schemas.

## Definition of done

- [ ] An OpenAPI 3.1 (or AsyncAPI 3.0) spec is the committed source of truth, and contract changes appear in the PR diff.
- [ ] Spectral passes in CI with the project ruleset: operation descriptions, error response schemas, controlled tags, no orphan schemas.
- [ ] Every endpoint carries a validated success example and a validated failure example; errors follow RFC 9457 and are documented once as a family.
- [ ] Authentication is documented once, end to end, and linked from endpoints.
- [ ] Quickstart TTFS is measured and under 15 minutes; all snippets execute in CI against a sandbox.
- [ ] Docs are versioned with the API, and the changelog is written for consumers.
- [ ] Deprecations carry `Deprecation` and `Sunset` headers, `deprecated: true` in the spec, and documented dates with migration steps.
- [ ] The docs pipeline runs spec lint, example validation, snippet execution, link check, prose lint, breaking-change detection, and a preview deploy on every PR.
