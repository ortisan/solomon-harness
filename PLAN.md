# PLAN.md: feat(ui): cross-project delivery cockpit (epic)

Problem statement:
The harness manages many projects on one machine, but each project's board and delivery memory are deliberately isolated: every project is its own tenant with its own memory database, so memory never leaks between projects. There is no place to see across that boundary. A portfolio delivery lead overseeing several solomon-harness-managed projects needs a single cockpit to aggregate every project's board and delivery metrics. Refs #44.

Proposed change and the boundary it touches:
This is the parent tracking epic for the cross-project delivery cockpit. It coordinates several INVEST child slices (#53-#57, #59) that vertical-slice the UI, logic, and data. As the parent tracking epic, its start marks the transition of the overall cockpit feature to "In Progress".

Target files:
- docs/solomon-workflow.md

Edge cases as observable outcomes:
- Tenant isolation breach (R-01): verified by isolation guardrails on child slices.
- Multi-user authentication/access control (D-05): currently out of scope for v1.

TDD breakdown:
1. **Red**: Define the epic visibility test in tests suite.
2. **Green**: Verify cockpit_read.py is importable and passes tests.

STRIDE notes:
- **S**poofing / **T**ampering / **I**nformation Disclosure: The read-only Aggregation Layer uses DatabaseClient to query per-tenant stores separately on demand (compose-never-join), preventing cross-tenant leakage.
- **D**enial of Service: Timeout-bounded concurrency prevents unreachable tenants from stalling cockpit queries.

Verification criteria:
- All unit and integration tests run and pass.
- Epic status is updated in project memory.
