## SOLID and structural discipline


Apply SOLID at the boundaries you design, and name the principle when you cite it in review:

- **SRP** — one reason to change per module. If a class changes for both a pricing rule and a report format, split it.
- **OCP** — extend behavior through new implementations of an abstraction, not by editing stable code. Watch for `if type == ...` ladders; they signal a missing polymorphic seam.
- **LSP** — a subtype must honor the supertype's contract: no strengthened preconditions, no weakened postconditions, no surprise exceptions. A subclass that throws `NotSupported` violates it.
- **ISP** — many focused client-specific interfaces over one fat interface. No client should depend on methods it never calls.
- **DIP** — high-level policy depends on abstractions; details depend on those same abstractions. This is exactly the Ports and Adapters rule above: the Core Domain owns the Port interfaces and the adapters depend on them.

Guard structure with fitness functions in CI: dependency-direction checks (ArchUnit for the JVM, import-linter for Python) that fail the build when an adapter is imported by the Core Domain, when a layer is skipped, or when a cyclic dependency appears. Architecture you cannot enforce automatically erodes by the next release.
