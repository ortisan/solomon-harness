---
name: architecture-styles
description: Governs choosing between Hexagonal ports and adapters as the project default, Clean Architecture, and functional-core-imperative-shell per bounded context, and enforcing the chosen dependency rule with a fitness function. Use when selecting or reviewing a bounded context's top-level architecture style before or during a design.
---

# Architecture Styles

Choose and enforce a top-level architecture style per bounded context, and record the choice and its trade-offs as an ADR. The project default is Hexagonal (ports and adapters) unless an ADR says otherwise; the goal of every style here is the same — keep the domain free of framework, transport, and persistence concerns so those can change without touching business rules.

## Hexagonal (ports and adapters) — the default

The domain sits at the center and talks to the outside only through ports (interfaces it defines); adapters implement those ports.

- Core domain: entities, aggregates, and use cases. Zero imports of web frameworks, ORMs, HTTP clients, or message libraries.
- Driving (inbound) ports: the API the outside calls to invoke a use case (e.g. `PlaceOrder`). Driving adapters: REST controllers, CLI handlers, queue consumers, scheduled jobs.
- Driven (outbound) ports: contracts the domain needs (e.g. `OrderRepository`, `PaymentGateway`). Driven adapters: DB clients, HTTP gateways, file/SMTP clients.
- Dependency rule: adapters depend on the domain; the domain depends on nothing external. Swapping Postgres for DynamoDB, or REST for gRPC, means writing a new adapter only — the core is untouched.
- Ports speak domain models, never transport- or DB-specific structures.

## Clean Architecture

Concentric layers with the dependency rule pointing strictly inward: Entities → Use Cases → Interface Adapters → Frameworks & Drivers. Source-code dependencies only ever point toward higher-level policy; inner layers know nothing of outer ones. Use cases orchestrate entities and define input/output boundaries (request/response models) that interface adapters map to and from. It is essentially Hexagonal with named layers; pick it when the team wants the explicit layer vocabulary and an enforced inward dependency direction.

## Functional core, imperative shell

A pure functional core (deterministic functions over immutable data, no side effects) wrapped by a thin imperative shell that does I/O and feeds data in and out. The core is trivially testable (inputs → outputs, no mocks); the shell holds all the effects (DB, network, clock, randomness). Prefer it for calculation- and rules-heavy domains (pricing, risk, transformations) where pure logic dominates and side effects are few and at the edges.

## Choosing and recording

- Default to Hexagonal. Choose Clean when the team values explicit layers; choose Functional core/imperative shell when the domain is computation-heavy.
- A style applies per bounded context, not necessarily to the whole system; a service can be Hexagonal while a pricing module is a functional core.
- Record the choice, the drivers, and the trade-offs as an ADR (see `architecture_decisions_in_project_memory`) so it is explicit and revisable.
- Enforce the boundary with fitness functions (see `evolutionary_architecture_fitness_functions`): a dependency rule that fails CI when the domain imports a framework keeps the style real over time.

## Common pitfalls

- "Hexagonal" with the ORM entity used as the domain entity, so persistence concerns leak into business rules. Keep a distinct domain model and map at the adapter.
- Ports defined in terms of HTTP/SQL types instead of domain types, which couples the core to a transport or store.
- Anemic use cases that just forward to a repository, adding layers with no policy. If a layer holds no rules, collapse it.
- A "functional core" that reads the clock, calls the network, or mutates shared state — those belong in the shell.
- Choosing a style by fashion rather than by drivers, and never writing the ADR, so the next team cannot tell what was intended or why.

## Definition of done

- [ ] The bounded context has one named architecture style, defaulting to Hexagonal.
- [ ] The domain has zero source dependencies on frameworks, ORMs, transports, or DB clients.
- [ ] Inbound and outbound ports are expressed in domain types; adapters do the mapping.
- [ ] The choice, drivers, and trade-offs are captured in an ADR.
- [ ] A fitness function enforces the dependency rule in CI.
