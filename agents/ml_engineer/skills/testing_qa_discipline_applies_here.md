# Testing: QA Discipline Applies Here

This skill governs how ML code is tested. Pipelines, transforms, metrics, and training loops are code and get the full red-green-refactor treatment — plus ML-specific tests for the failure mode ordinary software does not have: the model that runs cleanly, converges, and is silently wrong.

## Unit tests for transforms and metrics

- Test every feature transform against hand-computed golden values, including the ugly inputs: empty frames, a single row, all-NaN columns, unseen categories.
- Test metric functions against known cases: perfect predictions, inverted predictions, and the degenerate ones (single-class y_true for AUC, zero-variance denominator for Sharpe) — assert they raise or return the documented sentinel rather than a quiet NaN.
- Test the split logic directly: assert zero index overlap between train and test, groups never spanning the boundary, and every training timestamp strictly before the test window.
- Property-based tests with the `hypothesis` library earn their keep on transforms: a scaler's `inverse_transform(transform(x))` round-trips within 1e-9; encoders are permutation-invariant over row order.

## The overfit-a-tiny-batch smoke test

Before any real training run, prove the training loop can drive loss to near zero on 2 to 8 samples within a few hundred steps:

```python
def test_overfits_tiny_batch():
    xb, yb = fixture_batch(n=4)
    model, opt = build(seed=0)
    for _ in range(300):
        opt.zero_grad(); loss = criterion(model(xb), yb); loss.backward(); opt.step()
    assert loss.item() < 1e-3
```

A model that cannot memorize four samples has a wiring bug — misaligned labels, frozen or unregistered parameters, wrong loss reduction, a broken learning rate — and no amount of full-dataset training will reveal which. The test runs in seconds and belongs in CI.

## Invariance and directional tests

Behavioral tests catch models that score well but reason wrongly (the CheckList approach, Ribeiro et al. 2020):

- Invariance: perturbations that must not change the prediction beyond a small tolerance — renaming an entity id, shifting a timezone representation, reordering feature columns before the pipeline.
- Directional expectations: perturbations whose effect has a known sign — raising the price feature must not lower predicted churn probability; for monotone-constrained models, verify the constraint actually holds on a grid of inputs.

These run against a trained artifact on small fixture inputs and encode domain knowledge the aggregate metric cannot see.

## Regression thresholds in CI

Pin model quality in CI the way you pin behavior: a seeded end-to-end train-and-evaluate on a small committed fixture dataset, with the metric asserted against a stored threshold.

- With full determinism (fixed seeds, deterministic flags), assert near-exact: `abs(auc - 0.8412) < 1e-6`. Otherwise set the tolerance from measured seed noise — three standard deviations across 5 seeded runs — so the test fails on real regressions, not on jitter.
- Keep it fast (< 60 s) by shrinking the data and the model, not by skipping the path; mark the full-size variant `slow` for nightly runs.
- Update the threshold only through review, with the run that justifies the change linked; a threshold loosened in the same PR as the regression is the anti-pattern.

## Integration tests and mocking

Integration-test the train -> save -> load -> evaluate path end to end on a small fixture, asserting the loaded model reproduces the pre-save predictions. Mock all external services and data feeds — no live API, exchange, or database calls in tests — and make randomness deterministic via fixed seeds in every test. Add regression tests that fail if a known leakage pattern reappears (for example, a transform fit on the full dataset before the split); each leakage bug found in review becomes a permanent test.

## Backtest-logic tests

For trading models, unit-test the backtest mechanics: costs and slippage actually applied per trade, no look-ahead in signal alignment (signal at t trades at t+1), position sizing respected, and P&L reconciling against a hand-computed fixture episode. Validating the strategy itself — parameter robustness, capacity, statistical significance of the edge — is `quant_trader`'s responsibility; hand off the tested backtest engine and the fixtures.

## Common pitfalls

- Testing only the happy path of transforms and skipping empty/NaN/unseen-category inputs.
- Metric functions returning NaN silently on degenerate inputs instead of raising.
- Launching full training without the tiny-batch overfit test, then debugging wiring on the expensive run.
- CI that checks the pipeline runs but never checks the metric, so quality regressions merge green.
- Regression tolerances guessed instead of derived from measured seed variance — flaky at 1e-6 or blind at 0.05.
- Live network or database calls inside the test suite.
- Loosening a CI threshold in the same PR that caused the drop.

## Definition of done

- [ ] Transforms and metrics unit-tested against golden values, including degenerate and edge inputs.
- [ ] Split logic tested: no index overlap, no group straddling, strict temporal ordering.
- [ ] Tiny-batch overfit smoke test present and passing in CI.
- [ ] Invariance and directional tests encode at least the top domain expectations for the model.
- [ ] Seeded end-to-end regression test on a fixture dataset with a metric threshold derived from seed variance.
- [ ] All external services mocked; all test randomness seeded; save/load round-trip verified.
- [ ] Backtest mechanics covered by fixture-based tests; strategy validation handed off to quant_trader.
- [ ] Every leakage or correctness bug found in review has a corresponding permanent regression test.
