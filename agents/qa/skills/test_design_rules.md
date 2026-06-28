## Test design rules


- One behavior per test. The test name states the behavior: `test_<unit>_<condition>_<expected>`.
- Arrange-Act-Assert, visibly separated. No assertions in the Arrange block.
- Deterministic always: pin seeds (`random.seed`, `numpy.random.default_rng(seed)`, `PYTHONHASHSEED`), freeze time (`freezegun` / `time-machine`), and never depend on test execution order. Add `pytest-randomly` to surface order coupling.
- Test behavior through the public contract (ports), not private internals. Tests coupled to implementation rot on every refactor.
- Cover the boundaries: empty, single, max, off-by-one, negative, zero, null/None, malformed input, duplicate, and timezone/locale edges. For numeric paths add NaN, inf, and overflow inputs.
- Use property-based tests (`hypothesis`) for parsers, serializers, math, and invariants. Encode the invariant, let it generate counterexamples, and pin any shrunk failure with `@example`.
- Parametrize instead of copy-pasting (`@pytest.mark.parametrize`). Each case carries an `id`.
- Assert on specific values and error types (`pytest.raises(SpecificError, match=...)`), never a bare `assert result` or broad `Exception`.
