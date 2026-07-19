# J-01: Qualify a behavioral-evaluation candidate

An operator prepares isolated fixtures, records host-controlled runs, scores the
evidence, and compares the candidate with the baseline before deciding whether
the candidate is eligible for further review.

```mermaid
flowchart TD
    A[Open the behavioral evaluation guide] --> B[Prepare the pilot manifest]
    B -->|Valid manifest| C[Inspect 54 isolated host requests]
    B -->|Invalid or unsafe input| X[Receive a closed non-zero error]
    C --> D[Record baseline and candidate runs in the active host]
    D --> E[Score the recorded evidence]
    E -->|Complete evidence| F[Inspect attributable normalized results]
    E -->|Malformed evidence| Y[Receive a closed non-zero error]
    F --> G[Compare the paired matrix]
    G -->|Complete matrix| H[Read eligibility and named regressions]
    G -->|Incomplete matrix| Z[Receive no comparison report]
    C -->|Interrupt| R[Keep requests and scratch fixtures intact]
    R --> D
```

```yaml
id: J-01
name: Qualify a behavioral-evaluation candidate
value_statement: Decide from reproducible local evidence whether a candidate warrants further review.
personas:
  - Operator
entry_points:
  - docs/behavioral-evals.md
  - python -m solomon_harness.behavioral_evals prepare
actions:
  - action: Prepare the versioned manifest into a new scratch root.
    expected_observable: Exactly 54 unique requests point to bounded isolated fixtures.
  - action: Record each request with the active host and its containment policy.
    expected_observable: Every case arm and repetition has one attributable recording.
  - action: Score the complete recording artifact.
    expected_observable: Structural verdicts and nullable telemetry are emitted deterministically.
  - action: Compare the paired baseline and candidate results.
    expected_observable: Eligibility and each baseline-stable regression are named explicitly.
goal: Decide whether the candidate is eligible for later adoption work.
true_end_state: A persisted comparison report names the decision and regression evidence without changing protected project state.
exit: The operator retains the manifest recordings normalized results and comparison report for review.
abandonment:
  at_step: After preparation and before every host recording is complete.
  how: Stop the host run without invoking score or compare.
  resume: Continue from the persisted requests and create a complete recording artifact before scoring.
crosses:
  - Active host model execution boundary
```
