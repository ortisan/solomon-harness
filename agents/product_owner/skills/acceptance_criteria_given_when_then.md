## Acceptance criteria: Given-When-Then


Write acceptance criteria in Gherkin so QA can turn them into tests directly:

```
Scenario: <short name>
  Given <precondition / state>
  When <action>
  Then <observable, checkable result>
```

Rules:
- Cover the happy path, the boundary values, and at least one failure path per story. A story with only happy-path criteria is incomplete.
- Make every Then assertion observable and specific. "Then it is fast" is rejected; "Then the response returns within 400 ms at p95" is accepted.
- State exact values: counts, limits, timeouts, error codes, empty states, permission-denied states.
- Negative space is part of the contract. Define what must NOT happen (no duplicate charge, no PII in logs).
- Acceptance criteria are frozen at sprint start. Changes after that go through the scope-change protocol, not silent edits.
