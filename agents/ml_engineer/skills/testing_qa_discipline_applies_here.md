## Testing (QA discipline applies here)


- Unit-test feature transforms, the split logic (assert no index overlap between train and test), and metric functions against known inputs.
- Integration-test the train -> evaluate path end to end on a small fixture.
- Mock all external services and data feeds: no live API, exchange, or database calls in tests. Make randomness deterministic in tests via fixed seeds.
- Add explicit tests for backtest logic and parameters: cost/slippage applied, no look-ahead, correct position sizing, P&L reconciles.
- Add regression tests that fail if a known leakage pattern reappears (e.g. a transform fit on the full set).
