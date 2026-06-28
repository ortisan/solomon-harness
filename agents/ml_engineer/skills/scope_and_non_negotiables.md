# ML Engineer Best Practices

Purpose: a concrete standard for training, validating, and shipping ML and DRL models in this project without overfitting, data leakage, or numerical faults.

## Scope and non-negotiables


Every model that leaves your workstation must satisfy all of these before it is considered done:

- A written Model Hypothesis (see below) committed alongside the code.
- Cross-validation results plus a held-out out-of-sample test the model never touched during tuning.
- A leakage audit with no open findings.
- Shape, divide-by-zero, and overflow guards on every critical tensor operation.
- A reproducible run: fixed seeds, pinned dependencies, recorded dataset version and config.
- Unit and integration tests, with all external services mocked.
