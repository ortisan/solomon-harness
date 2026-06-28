# Mocking and Isolation

Test doubles let a unit or integration test run without the slow, flaky, or unowned dependency a component talks to: an HTTP API, a payment gateway, a clock, a queue. The skill is choosing the right double at the right seam so the test is fast and deterministic without going blind to real failures. Get it wrong and the suite is green theater: it passes because it only ever talks to a hand-built fake that drifted from the real provider months ago. This gates `/solomon-review` because over-mocked tests pass through coverage gates while asserting nothing a user would notice. Where each kind of double sits across the pyramid is owned by `the_test_pyramid_target_distribution`; what to keep real at the integration and E2E layers is owned by `integration_and_e2e_testing`. This file owns the doubles themselves and the boundary you attach them to.

## The Meszaros test-double taxonomy

Gerard Meszaros (xUnit Test Patterns) names five doubles. Pick by what the test needs to assert, not by habit.

- **Dummy**: a placeholder passed to satisfy a signature, never used. A `None` user-agent or an unread config object.
- **Stub**: returns canned answers to calls made during the test. Use for state verification: drive the system under test down a branch by feeding it a fixed response. A `get_rate()` that always returns `1.5`.
- **Spy**: a stub that also records how it was called, inspected after the fact. Use when you must verify an outgoing call happened but do not want to fail the run inside the call itself.
- **Mock**: pre-programmed with expectations and self-verifying; the call shape is the assertion and a wrong/absent call fails the test. Use sparingly, only for interactions that are the contract (an email was sent, a payment was captured).
- **Fake**: a working but lightweight implementation, in-memory and real logic. `fakeredis`, an in-memory repository, SQLite for a Postgres-shaped store. Use for collaborators you call many times where a stub chain would be unreadable.

Rule of thumb: prefer stubs and fakes for query-style collaborators (you read from them) and mocks only for command-style ones (you cause a side effect). Asserting call shape on a query is how change-detector tests are born.

## Mock at the boundary you own

Do not mock what you do not own. Patching a third-party SDK's internals (`stripe.api_requestor`, `boto3` client internals) couples your tests to a library's private structure, and when the vendor changes it your green tests still pass against a fiction. Wrap the SDK behind a port (an interface you define), test your code against a fake of that port, and cover the thin adapter that talks to the real SDK with a separate, narrow integration test.

```python
# Port you own — the seam your domain depends on.
from typing import Protocol

class PaymentGateway(Protocol):
    def charge(self, cents: int, token: str) -> str: ...  # returns charge id

# Adapter wrapping the unowned SDK (tested separately at the edge).
class StripeGateway:
    def __init__(self, client): self._client = client
    def charge(self, cents: int, token: str) -> str:
        return self._client.PaymentIntent.create(amount=cents, source=token).id

# Fast unit test: fake the PORT, never touch Stripe's module tree.
class FakeGateway:
    def __init__(self): self.charges = []
    def charge(self, cents, token):
        self.charges.append((cents, token)); return "ch_test"

def test_checkout_charges_total():
    gw = FakeGateway()
    checkout(cart=Cart(total_cents=4200), gateway=gw)
    assert gw.charges == [(4200, "tok_visa")]
```

The domain test never imports `stripe`. The real SDK is exercised once, where the adapter lives, against the contract checks below.

## Tools: patch at the right seam

- **`unittest.mock` / pytest `monkeypatch`**: patch where the dependency is *used*, not where it is defined: `patch("billing.service.gateway")`, not `patch("stripe.PaymentIntent")`. Always pass `autospec=True` or use `create_autospec` so the double rejects calls that do not match the real signature; a mock with a free-form interface gives a false pass when the real signature drifts.
- **HTTP with `responses` (requests) or `respx` (httpx)**: register every expected call; configure the suite so an unmatched request raises instead of escaping to the network. `respx` with `assert_all_called=True` fails the test when a registered route was never hit, catching dead stubs.
- **AWS with `moto`**: `@mock_aws` gives in-memory S3/DynamoDB/SQS that honor the real boto3 API, far better fidelity than hand-mocking `boto3.client`. For richer multi-service flows use `localstack` via Testcontainers (owned by `integration_and_e2e_testing`).
- **In-memory fakes over deep mock chains**: `fakeredis` for Redis, SQLite or an in-memory repo for storage. A test with `mock.return_value.cursor.return_value.fetchone.return_value = ...` is unreadable and asserts the call topology, not behavior. A fake replaces the chain with real logic. Reserve real containerized services for the integration layer per `integration_and_e2e_testing`.

```python
import httpx, respx

@respx.mock(assert_all_called=True)
def test_fetches_rate_from_fx_api(respx_mock):
    route = respx_mock.get("https://fx.example/usd/eur").mock(
        return_value=httpx.Response(200, json={"rate": 0.91})
    )
    rate = FxClient(httpx.Client()).usd_to_eur()
    assert rate == 0.91
    assert route.called                 # outgoing call verified
    assert route.calls.last.request.headers["accept"] == "application/json"
```

Here the response is a *stub* (canned body) and `route.called` is a *spy* assertion. No `mock.patch` of httpx internals; the interception sits at the HTTP boundary, the seam you actually own.

## Consumer-driven contract tests catch mock drift

The danger of the stub above: it encodes *your belief* about the FX provider's response. If the provider renames `rate` to `rate_bps`, the stub still returns `{"rate": 0.91}` and the test stays green while production breaks. A consumer-driven contract test closes that gap. With `pact-python`, the consumer test emits a pact file describing each interaction it depends on (request shape, the response fields it reads). The provider then replays that pact against its real handlers in its own pipeline, fulfilling each `given(...)` provider state; if the provider drops or renames a field the consumer relies on, the provider's verification fails before deploy. The mechanics, Pact Broker publication, and `can-i-deploy` gating are owned by `integration_and_e2e_testing`; the point *here* is that a contract test is what keeps a stub honest. Stub for speed at the unit layer, and back the same boundary with one contract so the fake cannot silently diverge from the real provider.

## Deterministic seams: inject clock, uuid, random

Nondeterminism is a test defect. Do not assert against `datetime.now()`, `uuid4()`, or unseeded `random` and then patch globals reactively. Build the seam in: pass a clock, an id factory, and a seeded RNG as dependencies, the same way the gateway is injected above.

```python
def test_token_expiry_uses_injected_clock():
    clock = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
    token = issue_token(ttl=timedelta(hours=1), now=clock)
    assert token.expires_at == datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
```

When you cannot thread a clock through (legacy code), `freezegun`'s `@freeze_time("2026-01-01")` or `time-machine` (faster, C-backed) pins wall-clock locally. Seed RNG explicitly (`random.Random(1234)`) rather than patching `random.random`, and inject a uuid factory returning a known sequence. Time and id control at the upper layers is owned by `integration_and_e2e_testing`; the rule shared across both is identical: control time and randomness through a seam, never assert against the live global.

## The over-mocking smell

A test that asserts call shape instead of observable behavior is a change-detector: it fails on every refactor that keeps behavior identical, training the team to update tests mechanically until they stop catching real defects. Symptoms: more `assert_called_with` lines than `assert` lines on outputs; mocks returning mocks (`mock.x.y.z`); a test that mirrors the implementation call-by-call so it can only ever pass against the code as currently written. Cure: assert the result or the one real side effect (the charge happened), fake collaborators rather than mocking them, and reserve `assert_called_*` for genuine command boundaries. If a test breaks under a behavior-preserving refactor, it was testing structure. Whether the doubles you kept are actually catching bugs is something `mutation_testing` (sibling skill) measures: a stub that lets a mutant survive is a stub asserting nothing.

## Common pitfalls

- Patching a third-party SDK's internal module instead of a port you own; the vendor refactors and your green test now asserts a fiction.
- `mock.patch` at the definition site (`patch("stripe.PaymentIntent")`) rather than the use site (`patch("billing.service.gateway")`), so the real code path is never rerouted.
- Mocks without `autospec`/`create_autospec`, accepting calls the real object would reject, producing a green test against a drifted signature.
- Deep mock chains (`m.return_value.cursor.return_value.fetchone...`) where an in-memory fake would be readable and assert behavior.
- Stubs that encode an assumed provider response with no contract test behind them; the provider renames a field and the stub stays green while production breaks.
- Asserting `assert_called_with` on query-style collaborators, turning the test into a change-detector that fails on every harmless refactor.
- Patching `datetime.now`/`uuid4`/`random` globally instead of injecting a clock, id factory, and seeded RNG through a seam.
- Letting an unmatched HTTP request escape to the real network; configure `responses`/`respx` to fail on unregistered calls and on registered-but-uncalled routes.
- Mocking the database or broker you own at the integration layer; that fidelity boundary is owned by `integration_and_e2e_testing` (use a real container).

## Definition of done

- [ ] Each double is the minimal Meszaros kind for the job: stub/fake for queries, mock only for command-style side effects that are the contract.
- [ ] No unowned third-party SDK is patched internally; it sits behind a port that is faked in unit tests, with the adapter covered separately at the edge.
- [ ] Patches target the use site, every `Mock` uses `autospec`/`create_autospec`, and the suite fails on unmatched and on registered-but-uncalled HTTP routes.
- [ ] HTTP is intercepted with `responses`/`respx`, AWS with `moto`/localstack, and deep mock chains are replaced by in-memory fakes (`fakeredis`, SQLite).
- [ ] Every stubbed external provider boundary is backed by a consumer-driven `pact` contract per `integration_and_e2e_testing`, so the stub cannot silently drift.
- [ ] Clock, uuid, and randomness are injected through seams (or pinned with `freezegun`/`time-machine` and seeded RNG); no assertion runs against a live global.
- [ ] No test asserts call shape where it could assert behavior; doubles are validated by `mutation_testing` so surviving mutants reveal stubs that assert nothing.
- [ ] No real API keys, live endpoints, or `sleep`-based waits appear in any test; ownership of the database/broker fidelity boundary is deferred to `integration_and_e2e_testing`.
