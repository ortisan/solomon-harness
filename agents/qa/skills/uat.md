# User Acceptance Testing and the Sign-Off Gate

User acceptance testing (UAT) is the validation step that answers a different question from every test below it: not "does the code work as built" but "did we build the thing the business actually needs". It is the last gate before a `release/*` branch ships, and it is owned by the business, not engineering. At the `/solomon-review` stage QA does not pass UAT itself; QA facilitates it, scripts the cases from acceptance criteria, runs them on a production-like environment, records defects against a fixed severity scale, and captures the sign-off that converts a green technical pipeline into a release decision. This skill owns that gate and the defect-severity scale used at release. The requirement-to-test mapping is owned by `test_planning_and_traceability`; the published gate report by `qa_report_the_required_output`.

## Validation versus verification

ISO/IEC/IEEE 29119 and the V-model separate two activities that teams routinely conflate.

- Verification (did we build it right): unit, integration, and system tests prove the implementation matches the specification. These run against the spec and are owned across `the_test_pyramid_target_distribution`, `integration_and_e2e_testing`, and `test_design_rules`.
- Validation (did we build the right thing): UAT proves the delivered behaviour satisfies the user's real need and the original business intent. A system can pass 100 percent of verification tests and still fail UAT because the acceptance criteria themselves missed the user's job-to-be-done.

The practical consequence: a UAT failure is often a requirements defect, not a code defect. Route it back to the product_owner via `log_issue` rather than filing it as a bug against the build. Verification failures stay in the engineering loop; validation failures escalate to whoever owns scope.

## Deriving cases from acceptance criteria, not the implementation

UAT cases come from the acceptance criteria and user stories, never from reading the code. Deriving cases from the implementation re-asserts what the system already does and is structurally blind to a feature that was built to the wrong intent.

Pull the Given/When/Then criteria and their stable IDs (for example `AC-CHK-04`) from the product_owner outputs, the same basis `test_planning_and_traceability` uses. Express each UAT case as a BDD/Gherkin scenario tied to its AC-ID so a business reader can confirm the scenario matches their intent before a single step runs, and so the scenario links into the traceability matrix owned by `test_planning_and_traceability`.

```gherkin
# AC-CHK-04: a returning customer can redeem one valid coupon at checkout
Feature: Coupon redemption at checkout
  Scenario: Returning customer redeems a single valid coupon  # -> AC-CHK-04
    Given a returning customer "anon_4471" with a cart subtotal of 120.00 EUR
    And an active coupon "SAVE20" granting 20 percent off, not yet used by this customer
    When the customer applies "SAVE20" at checkout
    Then the order total is 96.00 EUR
    And the coupon is marked redeemed for "anon_4471"
    And a second attempt to apply "SAVE20" is rejected with "coupon already used"
```

Keep the steps in the user's language (cart, checkout, coupon), not the system's (POST /orders, FK constraint). If a business stakeholder cannot read the scenario and agree it is what they asked for, it is not a UAT case yet.

## Production-like environment and realistic data

UAT runs on a staging or pre-production environment that mirrors production topology, configuration, and integrated third-party endpoints (payment sandbox, real SSO provider, real message bus), never against the unit-level test doubles described in `mocking_and_isolation_mock_all_external_services`. Mocks are correct for verification and wrong for validation: they cannot surface latency, real provider error shapes, schema drift, or configuration gaps, which are exactly the failures UAT exists to catch.

Data must be realistic and anonymized. Production-shaped volume and edge distributions, with PII removed or synthesised to satisfy GDPR/PCI obligations. Mask with a deterministic tool (`faker` for synthesis, format-preserving masking for card/IBAN fields) so referential integrity survives, and pin seeds and the clock so a UAT failure reproduces. Note the environment, build id, commit SHA, and dataset snapshot on every run; an unrecorded environment makes a pass unauditable.

## The UAT case table

Each UAT case is scripted with preconditions, steps, data, the expected result, the observed actual, a pass/fail verdict, and the business sign-off. The actual and sign-off columns are filled by the business tester during execution, not pre-filled by QA.

| Case ID | AC ID | Preconditions | Steps | Test data | Expected | Actual | Pass/Fail | Sign-off |
|---------|-------|---------------|-------|-----------|----------|--------|-----------|----------|
| UAT-CHK-04-01 | AC-CHK-04 | Returning customer, cart 120.00 EUR, coupon SAVE20 active | Apply SAVE20; confirm total; re-apply SAVE20 | anon_4471, SAVE20, 20% | Total 96.00 EUR; second apply rejected | 96.00 EUR; rejected | Pass | J. Okoro (PO) 2026-06-27 |
| UAT-CHK-04-02 | AC-CHK-04 | Returning customer, coupon already redeemed | Apply SAVE20 | anon_4471, SAVE20 | Rejected "coupon already used" | Applied, total reduced | Fail | J. Okoro (PO) 2026-06-27 |
| UAT-CHK-07-01 | AC-CHK-07 | Guest checkout, expired coupon | Apply OLD10 | guest, OLD10 (expired) | Rejected "coupon expired" | Rejected "coupon expired" | Pass | J. Okoro (PO) 2026-06-27 |

The failing row UAT-CHK-04-02 becomes a defect with the severity assigned below and a row in the traceability matrix (`test_planning_and_traceability`), so the reader moves criterion to case to defect to severity in one hop.

## The sign-off gate and roles

UAT sign-off is a business decision with named accountability, not a QA rubber stamp.

- The product_owner or a designated business representative executes or witnesses the cases and signs off. Their signature is the assertion that the delivered behaviour meets the need.
- QA facilitates: prepares the environment and anonymized data, scripts the Gherkin cases from the AC-IDs, trains testers, observes execution, and records every actual result and defect.
- Sign-off is per release scope and recorded against the specific commit SHA and build id, so it cannot be reused for a later build. Persist the decision with `save_decision` and hand it to the release owner via `log_handoff`, referencing the gate report assembled in `qa_report_the_required_output`.

A verbal "looks good" is not sign-off. The artifact is the signed case table plus the explicit Go/No-Go, which feeds the gate decision in `qa_report_the_required_output`.

## Defect severity scale and alpha/beta criteria

This skill owns the release severity scale. Severity measures user/business impact and is independent of priority (the fix-order decision lives in `defect_triage_and_lifecycle`).

| Severity | Definition | Release gate |
|----------|------------|--------------|
| Blocker | Core flow unusable, no workaround; data loss or security exposure | Blocks release |
| Critical | Major function broken or wrong result on a primary path; workaround painful or none | Blocks release |
| Major | Significant function impaired; an acceptable workaround exists | Conditional: needs PO waiver to ship |
| Minor | Limited impact, cosmetic logic, or a secondary path; easy workaround | Does not block |
| Trivial | Cosmetic, wording, alignment; no functional effect | Does not block |

Any open Blocker or Critical is an automatic No-Go. A Major ships only with a recorded product_owner waiver and a tracked follow-up issue. This aligns with the P1-first execution order in `test_planning_and_traceability` and the lifecycle states in `defect_triage_and_lifecycle`.

Phased acceptance uses explicit entry and exit criteria so the gate is not subjective:

- Alpha entry: feature-complete for the in-scope AC-IDs, all verification suites green, environment provisioned. Alpha exit: no open Blocker, all Critical triaged with owners, Must-have criteria demonstrated at least once.
- Beta entry: alpha exit met, anonymized production-shaped data loaded, real third-party integrations connected. Beta exit: zero open Blocker/Critical, every Must-have AC-ID signed off, Major defects either fixed or waived, and the signed case table archived.

## Common pitfalls

- Running UAT against unit mocks instead of real integrated endpoints, so provider error shapes and configuration gaps surface only in production.
- Writing cases from the code, which can only confirm the system does what it already does and never that it does what the user needed.
- QA signing off in place of the business, removing the only person accountable for whether the right thing was built.
- Using real customer PII in staging, breaching GDPR/PCI when anonymized synthesis would have served.
- Conflating severity with priority, so a cosmetic-but-urgent item and a Blocker get argued in the same column; keep severity here and priority in `defect_triage_and_lifecycle`.
- Treating a UAT failure as a code bug when it is a requirements defect, and fixing the build instead of returning the criterion to the product_owner via `log_issue`.
- Accepting a verbal sign-off with no signed case table, commit SHA, or dataset snapshot, leaving the release decision unauditable.
- Shipping a Major defect with no recorded waiver and no follow-up issue, so the known gap silently becomes permanent.

## Definition of done

- [ ] Every in-scope Must-have acceptance criterion has at least one UAT case expressed as Gherkin and tied to its AC-ID, derived from the criteria and not the implementation.
- [ ] UAT ran on a production-like environment with real integrated endpoints and realistic anonymized data; environment, build id, commit SHA, and dataset snapshot are recorded.
- [ ] Each case table row carries preconditions, steps, data, expected, actual, pass/fail, and a business sign-off filled during execution.
- [ ] Every defect is logged with a severity from the Blocker/Critical/Major/Minor/Trivial scale and reproduction steps; severities link to the matrix in `test_planning_and_traceability`.
- [ ] No open Blocker or Critical remains; any shipped Major has a recorded product_owner waiver and a tracked follow-up issue.
- [ ] The product_owner or business representative signed off per release scope against the specific build; the decision is persisted with `save_decision`.
- [ ] The Go/No-Go and signed case table are handed to the release owner via `log_handoff` and folded into the gate report in `qa_report_the_required_output`.
