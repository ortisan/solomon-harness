## Mocking and isolation (mock all external services)


- Patch at the boundary where the dependency is used, not where it is defined: `patch("module_under_test.client")`, not the library's own module.
- HTTP: intercept with `responses`, `respx` (httpx), or `requests-mock`. Register every expected call and assert it was made. Unmatched requests must fail the test, never hit the network.
- Use `autospec=True` (or `create_autospec`) so mocks reject calls that do not match the real signature. A green test against a drifted signature is a false pass.
- Assert the interaction, not just the return: `assert_called_once_with(...)`, argument captors, call counts and order when order matters.
- Databases and brokers: prefer ephemeral real instances via `testcontainers` for integration tests; reserve in-memory fakes (`fakeredis`, SQLite) for fast unit-level checks. Document which fidelity each test buys.
- Build fixtures with factories (`factory_boy` / `faker`) over hand-rolled dicts so test data stays valid as schemas evolve.
- Forbidden in tests: real API keys, live endpoints, `sleep`-based waits (poll with a timeout instead), and shared mutable global state between tests.
