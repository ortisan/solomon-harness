---
name: acceptance-criteria-given-when-then
description: Governs writing acceptance criteria in Gherkin Given-When-Then with exact values, requiring happy-path, boundary, and failure-path scenarios where every Then asserts an observable result. Use when drafting or reviewing a story's acceptance criteria before it is marked Ready.
---

# Acceptance Criteria With Given-When-Then

Write acceptance criteria in Gherkin (Given-When-Then) with exact values so QA can turn each scenario into a test without guessing intent. A story is not ready until its criteria cover the happy path, the boundary values, and at least one failure path, and until every Then asserts something observable and specific. Vague criteria are the most common reason a "done" story comes back.

## The rules

```gherkin
Scenario: <short, specific name>
  Given <precondition / starting state>
  When <the single action under test>
  Then <observable, checkable result>
```

- Cover the happy path, the boundary values, and at least one failure path per story. A story with only happy-path criteria is incomplete and must be sent back.
- Make every Then observable and specific. "Then it is fast" is rejected; "Then the response returns within 400 ms at p95" is accepted.
- State exact values: counts, limits, timeouts, currency amounts, error codes, empty states, permission-denied states. A reader must be able to compute the expected result.
- Negative space is part of the contract. Define what must NOT happen (no duplicate charge, no PII in logs, no second discount stacked).
- One When per scenario. Multiple actions in one scenario hide which step failed.
- Acceptance criteria are frozen at sprint start. Changes after that go through the scope-change protocol, not silent edits.

## Rejected vague Then vs accepted specific Then

The same scenario, written badly and well:

```gherkin
# REJECTED — not checkable; QA cannot derive a pass/fail
Scenario: Discount applied
  Given a cart with a code
  When the shopper applies the code
  Then the discount is applied correctly

# ACCEPTED — exact inputs and exact expected outputs
Scenario: Valid 20% code on a qualifying order
  Given a cart with subtotal $80.00
  And the code "SAVE20" is active on 2026-06-28
  When the shopper applies "SAVE20"
  Then the discount line shows -$16.00
  And the order total is $64.00
  And the response returns within 400 ms at p95
```

"Applied correctly" forces QA to invent the rule; the accepted version states it. Every Then here is a value an automated test can assert.

## Worked multi-scenario example

One story, the full set: happy path, two boundaries, a failure path, a cap boundary, and negative space. The underlying business rule is stated once so the numbers are not magic.

Business rule: code `SAVE20` gives 20% off, valid 2026-01-01 to 2026-06-30, requires subtotal >= $50.00, caps the discount at $100.00, and only one code is allowed per order.

```gherkin
Feature: Redeem a percentage discount code at checkout

  # HAPPY PATH
  Scenario: Valid code on a qualifying order
    Given a cart with subtotal $80.00
    And "SAVE20" is active on 2026-06-28
    When the shopper applies "SAVE20"
    Then the discount line shows -$16.00
    And the order total is $64.00

  # BOUNDARY — exactly at the minimum threshold (passes)
  Scenario: Order subtotal equals the $50.00 minimum
    Given a cart with subtotal $50.00
    When the shopper applies "SAVE20"
    Then the discount line shows -$10.00
    And the order total is $40.00

  # BOUNDARY — one cent below the minimum (rejected)
  Scenario: Order subtotal one cent below the minimum
    Given a cart with subtotal $49.99
    When the shopper applies "SAVE20"
    Then no discount is applied
    And the message reads "Add $0.01 to use code SAVE20 (minimum $50.00)"
    And the order total stays $49.99

  # BOUNDARY — discount cap
  Scenario: Discount is capped at $100.00
    Given a cart with subtotal $600.00
    When the shopper applies "SAVE20"
    Then the discount line shows -$100.00
    And the order total is $500.00

  # FAILURE PATH — expired code
  Scenario: Expired code is refused
    Given a cart with subtotal $80.00
    And "SAVE20" expired on 2026-06-30
    And the current date is 2026-07-01
    When the shopper applies "SAVE20"
    Then no discount is applied
    And the message reads "Code SAVE20 expired on 2026-06-30"
    And the API responds with HTTP 422

  # NEGATIVE SPACE — codes must not stack
  Scenario: A second code does not stack on the first
    Given "SAVE20" is already applied to the order
    When the shopper applies "WELCOME10"
    Then "WELCOME10" is rejected
    And the message reads "Only one code per order"
    And "SAVE20" remains applied and the total is unchanged
```

Why each scenario earns its place: the happy path proves the rule works; the $50.00 and $49.99 pair pins the boundary exactly (the most common source of off-by-one bugs); the $600.00 case proves the cap fires at $100.00 rather than computing $120.00; the expired-code case proves the failure path returns a specific message and status; and the stacking case nails the negative space so a second code cannot silently double the discount. Together they are a contract QA can automate line for line.

## Common pitfalls

- Only happy-path scenarios, no boundary or failure path: the story looks done and breaks in production at the edges. Reject until boundaries and at least one failure are covered.
- A Then that is not observable ("works correctly," "is fast," "looks right"): QA cannot pass or fail it. Demand an exact value, code, message, or threshold.
- Boundaries stated as a range instead of the exact edge (">= minimum") without the at-the-edge and just-below scenarios: the off-by-one stays untested. Pin $50.00 and $49.99, not "around $50."
- Multiple When steps in one scenario: when it fails you cannot tell which action broke. Split into one action per scenario.
- Missing negative space (no rule for double-charge, stacked codes, or PII in logs): the absent rule becomes a defect. State what must NOT happen.
- Error scenarios that omit the exact message and status code: QA cannot assert the failure, so it goes untested. Specify the message text and the HTTP/error code.
- Criteria edited after sprint start without the scope-change protocol: silent scope drift. Freeze at sprint start; route changes through the protocol.

## Definition of done

- [ ] Every story has at least one happy-path, one boundary, and one failure-path scenario in Given-When-Then.
- [ ] Every Then is observable and specific, with exact values (counts, amounts, timeouts, error codes, messages, empty/permission-denied states).
- [ ] Boundaries are pinned with at-the-edge and just-past-the-edge scenarios, not a vague range.
- [ ] Each scenario has a single When; one action under test per scenario.
- [ ] Negative space is defined: the criteria state what must NOT happen.
- [ ] Failure scenarios specify both the user-facing message and the error or HTTP status code.
- [ ] Criteria are frozen at sprint start; any later change went through the scope-change protocol.
- [ ] QA confirms each scenario is directly automatable from the stated values without further clarification.
