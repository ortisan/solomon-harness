# Integration and end-to-end testing

Own the upper two layers of the pyramid: integration tests that exercise real wiring against real backing services, and a thin top of end-to-end tests that prove a critical user journey works through the deployed system. The job here is not coverage breadth (that belongs to units, see `the_test_pyramid_target_distribution`) but confidence in the seams the unit layer cannot see: SQL that the ORM actually emits, the contract a consumer relies on, the redirect a browser actually follows. Keep these tests few, deterministic, and honest about what they prove, because every one is slower and more brittle than a unit test and pays for itself only by catching integration faults no faster test can.

## Layer scope and ratios

- Target roughly 20% integration and 10% E2E against ~70% unit. These are a budget, not a quota: when integration creeps toward 40% you are usually pushing logic up that belongs in fast unit tests; when E2E exceeds ~15% you are building the ice-cream cone and will pay in flake and slow CI.
- Integration tests one component plus one real adapter: repository against a real Postgres, publisher against a real Kafka, HTTP handler against a real router and serializer. Stub only what sits at the system edge (third-party HTTP APIs, payment gateways, SMS/email senders), never the database or message broker you control.
- E2E tests a whole path through the running system end to end: browser to API to database. Reserve it for revenue-critical or compliance-critical journeys (sign-up, checkout, login). A good rule: if a journey breaking would page someone, it earns an E2E test; otherwise push the assertion down a layer.
- Do not test the same logic at two layers. An E2E test that re-checks a validation rule already covered by a unit test buys nothing and adds a slow, flaky duplicate. Each layer asserts what only it can.

## Integration: real backing services with Testcontainers

Use real services in ephemeral containers, not mocks or shared staging databases. `testcontainers-python` 4.x starts a throwaway container per session, gives you the dynamically mapped port, and tears it down. This catches dialect-specific SQL, migration drift, and serialization bugs that an in-memory fake (SQLite standing in for Postgres) silently hides.

```python
import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_engine():
    # Pin the image tag; "latest" makes the suite non-reproducible across machines/CI.
    with PostgresContainer("postgres:16.4-alpine") as pg:
        engine = create_engine(pg.get_connection_url())
        run_migrations(engine)            # exercise the real migration path, not a hand-built schema
        yield engine

@pytest.fixture
def db(pg_engine):
    # One transaction per test, rolled back: fast isolation without re-seeding the whole DB.
    conn = pg_engine.connect()
    txn = conn.begin()
    yield conn
    txn.rollback()
    conn.close()

def test_order_repository_persists_and_reads_back(db):
    repo = OrderRepository(db)
    repo.save(Order(id="o-1", total_cents=4200))
    assert repo.get("o-1").total_cents == 4200
```

- Scope the container to the session (`scope="session"`) and isolate tests with a per-test transaction rollback, or truncate-between-tests. Starting a container per test is correct but slow; reuse the container, reset the data.
- Run migrations against the container rather than declaring the schema inline. This is where you catch a migration that compiles but corrupts data.
- Same pattern for Redis (`RedisContainer`, `redis:7.4`), Kafka (`KafkaContainer`, `confluentinc/cp-kafka:7.7.x`), and localstack for AWS. For brokers, produce then consume in the test and assert on the delivered message, including headers and partition key.
- Reuse containers locally with Testcontainers Ryuk/`reuse=True` to cut feedback time, but never rely on reuse in CI where each run must be clean.

## API and schema/OpenAPI validation

Test the HTTP surface through the real app, asserting both status and that the payload conforms to the published schema, not just to a hand-written expectation that can drift from the spec.

```python
import schemathesis

# Property-based: generate requests from the OpenAPI doc and assert every response
# matches the documented schema, status codes, and content type.
schema = schemathesis.openapi.from_path("openapi.yaml")

@schema.parametrize()
def test_api_conforms_to_spec(case):
    response = case.call_asgi(app)   # in-process ASGI; no network flake
    case.validate_response(response) # rejects undocumented fields, wrong types, bad status
```

- `schemathesis` 3.x drives the API from the OpenAPI/Swagger document and finds 500s, schema violations, and undocumented responses you would never enumerate by hand. Use it as a fuzz layer over a handful of explicit happy-path and error-path example tests.
- For explicit cases, validate the response body against the schema (`openapi-core`, or `jsonschema` against the component schema) so a backward-incompatible field rename fails a test instead of silently breaking clients.
- Assert error contracts too: a documented 422 with a specific body shape is part of the API and must be tested, not just the 200.

## Consumer-driven contract testing with Pact

When two services you own (or you-as-consumer plus a provider) talk over HTTP or messaging, a contract test catches breaking changes without a full integrated environment. The consumer declares the interactions it depends on; the provider verifies it satisfies them. This replaces brittle, slow cross-service E2E for most integration risk.

```python
# Consumer side (pact-python 2.x, Pact spec v3/v4). Generates a pact file.
from pact import Consumer, Provider

pact = Consumer("orders-web").has_pact_with(Provider("orders-api"), port=1234)

def test_get_order_contract():
    (pact
        .given("order o-1 exists")                 # provider state, set up on verify
        .upon_receiving("a request for order o-1")
        .with_request("GET", "/orders/o-1")
        .will_respond_with(200, body={"id": "o-1", "total_cents": 4200}))
    with pact:
        assert OrdersApiClient("http://localhost:1234").get("o-1").total_cents == 4200
```

- The consumer test produces a pact file; the provider replays it against its real handlers, fulfilling each `given(...)` provider state. The provider verifies the contract it must honor, not a copy the consumer invented.
- Publish pacts to a Pact Broker / PactFlow and gate deploys with `can-i-deploy`, so a provider change that breaks a live consumer fails the pipeline before release.
- Contract tests assert shape and semantics of the interaction, not business logic. Keep provider-state setup minimal and deterministic.
- Use contract tests as the default for service-to-service confidence; reserve true multi-service E2E for the one or two journeys that must be proven end to end.

## End-to-end: Playwright and Cypress

Browser and full-flow tests are the most expensive tests you own. Write the fewest that cover the critical journeys and make each one deterministic.

```ts
// Playwright 1.5x. Auto-waiting locators; no manual sleeps.
import { test, expect } from '@playwright/test';

test('user completes checkout', async ({ page }) => {
  await page.goto('/cart');
  await page.getByRole('button', { name: 'Checkout' }).click();
  await page.getByLabel('Card number').fill('4242424242424242');
  await page.getByRole('button', { name: 'Pay' }).click();
  // Assert on user-visible outcome, retried automatically until it appears or times out.
  await expect(page.getByText('Order confirmed')).toBeVisible();
});
```

- Prefer Playwright 1.5x for new work: parallel by default, cross-browser (Chromium/Firefox/WebKit), trace viewer for post-mortem, and built-in auto-waiting that removes the main source of flake. Cypress 14/15 remains fine for existing suites; do not rewrite a working one to chase fashion.
- Select by role and accessible name (`getByRole`, `getByLabel`), not CSS classes or XPath. Role selectors survive restyling and double as an accessibility check; brittle CSS selectors are the top cause of E2E churn.
- Stub only the true system edge (third-party payment, mail) at the network boundary (`page.route` / Cypress `cy.intercept`). Let the request hit your own API and database, otherwise the test stops being end-to-end.
- Drive setup through the API or a seed script, not through the UI. Logging in via the form in every test is slow and couples unrelated journeys; authenticate once and reuse storage state (`storageState`).

## Determinism and test data

Flake is a defect in the test, not the system. The upper layers are where flake breeds, so enforce determinism aggressively. Quarantine and root-cause flaky tests rather than masking them (see the qa `flaky_tests` skill); retries hide flake, they do not fix it.

- No fixed sleeps. Wait for a condition (element visible, row present, message consumed) with a bounded timeout. `sleep(2)` is both slow and racy. Auto-waiting locators and explicit polling replace it.
- Control time. Inject a clock or freeze it (`freezegun` in Python, `page.clock` / `cy.clock` in the browser) instead of asserting against `now()`. Tests that depend on wall-clock or "today" fail at midnight and across time zones.
- Make data setup explicit and isolated. Each test seeds exactly what it needs and rolls back or truncates after; never depend on data left by a previous test or on a shared mutable fixture. Cross-test ordering dependence is a latent flake.
- Stub external nondeterminism: random IDs, UUIDs, and external API responses are pinned at the edge so the same input gives the same result.
- Treat a green-only-on-rerun test as failing. A retry that "fixes" it is a smell, not a pass; investigate before merging.

## CI execution

- Start backing services as ephemeral containers in CI (Testcontainers inside the job, or service containers), never against shared staging. A test that mutates a shared environment is non-isolated and will flake or corrupt others' runs.
- Shard and parallelize: split the slow integration/E2E suites across CI workers (Playwright `--shard=1/4`, pytest-xdist `-n auto`, Cypress parallelization). This keeps wall-clock low so the upper layers stay runnable on every PR, not just nightly.
- Retries are a smell, not a strategy. A single auto-retry to absorb genuine infra blips is defensible; two or three to get green is hiding a real defect. Cap retries at one and alert on any test that needs it.
- Gate merges on the full integration suite and the critical-journey E2E set; run the broad E2E/cross-browser matrix on a schedule or pre-release if it is too slow for every push. Publish pacts and run `can-i-deploy` in the pipeline.
- Capture artifacts on failure (Playwright trace, screenshots, container logs) so a CI-only failure is debuggable without a local repro.

## Common pitfalls

- Mocking the database or broker you own. An in-memory or SQLite stand-in hides dialect, migration, and serialization bugs; use a real containerized service. Mock only the external edge.
- Fixed `sleep`/`wait(2000)` to "fix" timing. Slow and still racy; wait on a condition with a bounded timeout instead.
- Re-asserting unit-level logic in an E2E test. Slow, flaky duplication with weak failure localization; assert it once at the lowest layer that can.
- E2E selectors bound to CSS classes or XPath. They break on every restyle; use role/label selectors.
- Logging in and seeding through the UI in every E2E test. Couples journeys and balloons runtime; seed via API and reuse stored auth state.
- `latest` image tags in Testcontainers. Non-reproducible across machines and over time; pin the exact tag.
- Tests that depend on data left by a prior test or on execution order. Latent flake; isolate with rollback/truncate per test.
- Treating cross-service E2E as the way to catch integration breaks. Slow and broad; use consumer-driven Pact contracts for service-to-service confidence and reserve E2E for whole-journey proof.
- Retries cranked to 3 to get a green build. That ships a known-flaky or broken test; cap at one and root-cause.
- Asserting against wall-clock time without a controllable clock. Fails at boundaries; freeze or inject time.

## Definition of done

- [ ] Integration tests run against real backing services (Testcontainers, pinned image tags), exercise the real migration path, and isolate state per test via transaction rollback or truncation.
- [ ] Only the true system edge (third-party HTTP, payment, mail/SMS) is stubbed; the database and message brokers you own are real in integration and E2E.
- [ ] API tests validate responses against the OpenAPI schema (e.g. `schemathesis` plus explicit happy/error-path cases), including documented error contracts.
- [ ] Service-to-service interactions are covered by consumer-driven Pact contracts, published to a broker and gated with `can-i-deploy`.
- [ ] E2E tests exist only for critical user journeys, use role/label selectors, seed via API with reused auth state, and assert user-visible outcomes.
- [ ] No fixed sleeps anywhere; waits are condition-based with bounded timeouts, and time-dependent assertions use a controllable/frozen clock.
- [ ] Layer ratios hold roughly 70/20/10 unit/integration/E2E per `the_test_pyramid_target_distribution`; no logic is asserted redundantly across layers.
- [ ] CI starts ephemeral services per run, shards/parallelizes the slow suites, caps retries at one (any retry alerts), and captures traces/logs on failure.
- [ ] Effectiveness of the upper layers is sampled with `mutation_testing` on the integration boundary so green is earned, not assumed.
