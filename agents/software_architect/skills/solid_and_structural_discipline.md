# SOLID and Structural Discipline

Apply SOLID at the boundaries you design rather than inside a single class, and name the violated principle whenever you reject a design, because an unnamed structural objection is opinion a peer can dismiss.

## The five principles at boundary scope

Cite the principle by name, paired with the smell that triggers it:

- SRP (Single Responsibility) — one reason to change per module, defined by the actor it serves. If a class changes for a pricing rule and for a report format, two actors own it; split along the actor. The smell is a module imported by unrelated subsystems.
- OCP (Open/Closed) — extend behavior by adding an implementation of an abstraction, not by editing stable code. The smell is an `if type == ...` / `switch (kind)` ladder that grows each time a case is added; it marks a missing polymorphic seam.
- LSP (Liskov Substitution) — a subtype must honor the supertype's contract: no strengthened preconditions, no weakened postconditions, no new exceptions the base never threw. A subclass that throws `NotSupportedError` for a base method is the canonical violation; it forces callers to type-check, which then breaks OCP too.
- ISP (Interface Segregation) — many client-specific interfaces over one fat interface. No client should depend on methods it never calls; a forced `raise NotImplementedError` is the tell that a fat port must be split.
- DIP (Dependency Inversion) — high-level policy and low-level detail both depend on an abstraction the policy owns. This is the Ports and Adapters rule (`architecture_styles`): the Core Domain declares the Port interface; the adapter implements it. Detail depends on policy, never the reverse.

These map onto the design-contract work (`design_contracts_as_component_boundaries`): SRP and ISP shape what a port exposes, LSP is what makes a contract substitutable across implementations, and DIP is what makes the contract — not the implementation — the thing consumers bind to.

## Package- and module-level cohesion and coupling

SOLID governs classes; Martin's package principles govern the modules an architect actually draws. Use them to decide where boundaries fall.

- Cohesion — REP (release/reuse equivalence), CCP (common closure: things that change together live together), CRP (common reuse: things used together live together). CCP is the workhorse: group by reason-to-change, not by technical kind.
- Coupling — ADP (acyclic dependencies: no cycles), SDP (stable dependencies: depend toward stability), SAP (stable abstractions: stable packages should be abstract). A cycle between packages is the first erosion symptom and is always a defect.

## The one structural rule that matters most: dependency direction

Pick the allowed dependency directions, forbid the rest, and let the build reject a single illegal import. At design time you state the rule; the executable enforcement lives in `evolutionary_architecture_fitness_functions` (ArchUnit for the JVM, import-linter or tach for Python, dependency-cruiser for JS/TS). Author the tooling there, not here.

### Worked dependency-direction rule

Take a hexagonal service with three packages: `domain` (policy + ports), `application` (use cases), `adapters` (REST, DB). The intended direction is inward toward `domain`.

Violation (DIP and the acyclic rule both broken):

```python
# domain/pricing.py  -- WRONG: policy importing detail
from adapters.postgres import OrderTable     # domain now depends on the DB driver
```

The domain can no longer be unit-tested without Postgres, swapping the store touches business rules, and a cycle appears the moment `adapters` imports `domain` back.

Corrected (the domain owns the abstraction, the adapter depends inward):

```python
# domain/ports.py
class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...

# domain/pricing.py  -- policy depends only on the port it owns
from domain.ports import OrderRepository

# adapters/postgres.py  -- detail depends on policy
from domain.ports import OrderRepository
class PostgresOrderRepository(OrderRepository): ...
```

The rule handed to the fitness function: `domain` may import nothing under `adapters`; `application` may import `domain` but not `adapters`; `adapters` may import both. A single import that breaks this fails CI, so the structure cannot erode quietly between releases.

## Common pitfalls

- Citing "this feels wrong" with no named principle in review, which a peer can override because no objective rule sits behind it; always name SRP/OCP/LSP/ISP/DIP.
- Grouping modules by technical kind (`controllers/`, `services/`, `models/`) instead of reason-to-change, which spreads one feature across every layer and breaks CCP; a reviewer rejects it because every change then touches many packages.
- A "DIP-compliant" design where the interface lives next to the implementation in the adapter package, so policy still depends outward; the abstraction must be owned by the consumer or domain.
- Treating SOLID as a class-level lint pass and ignoring package cycles, the real erosion symptom an architect is paid to catch.
- Stating a dependency-direction rule in prose but never encoding it as a blocking fitness function, so it is unenforced and decays; reviewers reject unenforceable architecture.
- Splitting a class to satisfy SRP into fragments that always change together, trading one smell for needless indirection; SRP is about actors, not file size.

## Definition of done

- [ ] Every structural objection in review names the specific principle (SRP/OCP/LSP/ISP/DIP) and the smell that triggered it.
- [ ] Module boundaries are drawn by reason-to-change (CCP), not by technical kind.
- [ ] No cyclic dependencies between packages; dependencies point toward stability and toward the domain.
- [ ] Ports are owned by the consumer or domain; adapters depend inward, so DIP holds at every integration point.
- [ ] The dependency-direction rule is stated and handed to `evolutionary_architecture_fitness_functions` to enforce as a blocking CI check.
- [ ] Fat interfaces are segregated so no client depends on methods it never calls.
