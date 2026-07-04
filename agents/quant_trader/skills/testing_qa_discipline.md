# Testing and QA Discipline

Quant code fails silently — a sign flip or an off-by-one bar produces plausible-looking PnL — so this skill mandates strict TDD with tests that assert exact known-good values for indicators, signals, and accounting, bit-for-bit determinism for backtests, and fully mocked market-data feeds so nothing depends on the network or the clock.

## TDD cycle

Red, Green, Refactor, always: write the failing test first, implement the minimum to pass, then refactor with the tests green. For quant work the Red test is usually a fixture with hand-computed numbers, and writing it first forces you to compute the expected value independently of the code under test — which is the whole defense against confirming your own bug.

## Indicator and signal tests against known-good values

- Test every indicator against published or hand-computed reference values, never against another run of the same implementation. Wilder's RSI has worked examples in the original text; EMA, ATR, MACD, and Bollinger values can be cross-checked against TA-Lib output pinned into the fixture (pin the values themselves, not a live TA-Lib call).
- Assert tightly: `pytest.approx(expected, rel=1e-9)` for float pipelines. Loose tolerances hide off-by-one-bar bugs, which shift values by roughly one bar's change and slip straight through a 1e-2 tolerance.
- Cover the warm-up region explicitly: the first `lookback - 1` bars must be NaN (or the documented convention), and the first defined value must match the reference. Warm-up off-by-one is the most common indicator bug.
- Signals get truth-table tests: a crafted price path where the expected entries and exits are enumerable by hand, asserted as an exact list of (timestamp, side) pairs.

## Backtest determinism tests

- Same config, same data snapshot, same seeds means bit-identical output. Assert it: run the backtest twice in-process and compare a SHA-256 over the serialized trade list and the equity-curve bytes.
- Pin a golden run: a small fixture backtest whose trade-list hash is committed; any diff fails CI and forces a deliberate golden update with a reviewable diff of the actual trades.
- Hunt nondeterminism at its known sources: dict or set iteration over instruments, wall-clock calls inside the engine, unseeded RNGs (including the ML framework's), and parallel reduction order. The determinism test catches all of them cheaply.
- Accounting golden tests: a known sequence of fills, costs, and prices must produce an exact, asserted PnL, equity curve, and Sharpe, hand-computed in the test's comments so a reviewer can re-derive them.

## Mocked market-data feeds

- No network in tests, ever. All external API calls and market-data services are mocked or replaced by fixture feeds, so unit and integration tests run offline and deterministically.
- Build a fixture feed that replays committed bars or ticks through the same interface as the live feed, so the engine cannot tell the difference; that interface parity is itself a test.
- Feed the nasty cases on purpose: gaps (halts, holidays), duplicate and out-of-order ticks, NaN rows, zero-volume bars, DST transitions and session boundaries, and a feed that stalls mid-session — which must trigger the staleness kill switch, not a hang.
- Contract tests at the vendor boundary: one thin, recorded test per vendor payload shape, so a vendor schema change fails one obvious test instead of silently corrupting downstream fixtures.

## Guard and edge-case tests

- Leakage guards get their own tests: a fixture with a deliberate lookahead (a feature built from bar t+1) must fail the pipeline's leakage assertion. The test proves the guard is alive.
- Numerical edges: zero-volatility windows, empty trade sets, a single-bar series, extreme prices, and all-NaN feature columns must return defined values or raise cleanly, never emit NaN PnL.
- The cost model is unit-tested in isolation: half-spread, impact (including the large-order square-root path), and fee components each against hand-computed values, before they meet the engine.
- Property-based tests (Hypothesis) for invariants: cash plus position value equals equity after every fill; no fill exceeds the participation cap; equity is unchanged on bars with no position and no costs.

## Common pitfalls

- Testing an indicator against the same library that computes it in production; the test can only confirm the bug.
- Loose tolerances (1e-2) that let off-by-one-bar errors pass.
- A "deterministic" backtest that diffs across runs because of dict ordering or an unseeded framework RNG, found only after results were reported.
- Live network calls in tests: green on one machine, red in CI, meaningless everywhere.
- Golden files updated blindly to make CI pass, deleting the information the diff carried.
- No warm-up-region assertions, so every indicator is silently shifted by one bar.

## Definition of done

- [ ] Every new indicator, signal, or accounting change started from a failing test with independently computed expected values.
- [ ] Indicator tests assert exact reference values (rel tolerance <= 1e-9) including the warm-up region; signals asserted as exact entry/exit lists.
- [ ] Determinism test green: a repeated run yields identical trade-list and equity hashes; a golden-run hash is committed and CI-enforced.
- [ ] All market-data and external services mocked; the fixture feed exercises gaps, out-of-order ticks, NaNs, DST boundaries, and staleness.
- [ ] A planted-lookahead test proves the leakage guard fires; numerical edge cases covered without NaN output.
- [ ] Cost model unit-tested in isolation, including the large-order impact path; portfolio invariants covered by property-based tests.
