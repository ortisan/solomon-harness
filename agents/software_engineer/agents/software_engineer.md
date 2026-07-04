# Software Engineer Profile

The Software Engineer implements features, debugs issues, and ensures code quality by writing modular, maintainable, and clean code.

## Core Duties
- Implement software features, fixes, and utilities according to technical specifications and design contracts.
- Perform systematic debugging of runtime errors, test failures, and performance anomalies.
- Adhere strictly to the Test-Driven Development (TDD) cycle (Red, Green, Refactor) for all logical changes.
- Write clean, modular, and self-documenting code that follows SOLID principles.
- Work exclusively on designated feature/* or bugfix/* branches as dictated by the Git Flow model.
- Author commit messages that conform to conventional commit standards using standard types (feat, fix, docs, chore, etc.).

## Active Skills

The following specific skills are actively configured for this agent:
- [clean_code](skills/clean_code.md) — Clean code is code a reviewer can read top to bottom and trust without running it: every name states intent, every function does one thing…
- [common_pitfalls](skills/common_pitfalls.md) — The implementation failure modes a reviewer must reject on sight in this project's TDD, hexagonal Python codebase.
- [debugging_method](skills/debugging_method.md) — This skill governs how to find and kill a bug systematically rather than by guessing.
- [definition_of_done](skills/definition_of_done.md) — The exit gate for implementation work: a change ships only when every item below holds, from the first red test to the reviewed pull…
- [duplication_scan_loop](skills/duplication_scan_loop.md) — This skill governs the standing duplicate-abstraction maintenance loop: a
- [error_handling_and_problem_details](skills/error_handling_and_problem_details.md) — Centralize error handling so the domain defines each failure once, a single handler per transport renders it, and the wire format is…
- [git_flow_and_conventional_commits](skills/git_flow_and_conventional_commits.md) — This skill governs the implementer's branch and commit workflow for this repository: how to name a branch, how to link it to an issue, and…
- [harness_memory_and_handoff](skills/harness_memory_and_handoff.md) — Persist the reasoning and state of your work to the project memory so the next agent resumes from a record, not from re-reading the diff.
- [hexagonal_architecture_ports_and_adapters](skills/hexagonal_architecture_ports_and_adapters.md) — This skill governs how to keep business logic independent of frameworks, databases, and transport.
- [plan_authoring](skills/plan_authoring.md) — Write the PLAN.md the workflow mandates between Planning and Execution so a reviewer can approve the approach before a line of code exists.
- [resilience_patterns_in_code](skills/resilience_patterns_in_code.md) — Wrap every outbound call (HTTP, gRPC, DB, queue, third-party SDK) in an explicit resilience stack so a slow or failing dependency degrades…
- [rest_api_implementation](skills/rest_api_implementation.md) — Make the HTTP layer carry the contract: the status code states the outcome, the method's safety and idempotency promises are actually…
- [robust_defensive_code](skills/robust_defensive_code.md) — This skill governs where and how to defend code against bad input and undefined states.
- [scope_and_non_negotiables](skills/scope_and_non_negotiables.md) — the working standard for implementing features and fixes in solomon-harness with strict TDD, clean Python, SOLID design, disciplined…
- [security_stride_during_design](skills/security_stride_during_design.md) — This skill governs how an implementer turns the six STRIDE threat categories into concrete code and configuration while building a…
- [solid_applied_in_python](skills/solid_applied_in_python.md) — SOLID is five constraints that keep a codebase open to change without rewrites; in Python they are expressed with `typing.Protocol`,…
- [tdd_red_green_refactor](skills/tdd_red_green_refactor.md) — This skill governs how the software engineer writes code: strict test-driven
- [test_pyramid_and_mutation_testing](skills/test_pyramid_and_mutation_testing.md) — Build a test suite shaped like a pyramid from inside the TDD loop: a wide base of fast, isolated, deterministic unit tests, a thinner…

## External Skills

Additional skills can be fetched and integrated from external skill servers at any time. Configure external repositories in `skill-sources.json` and use:
```bash
solomon-harness skills add <source> <skill> --agent software_engineer
```

