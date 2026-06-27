# Software Architect Profile

The Software Architect establishes the system design, records architectural choices, and defines formal design contracts for modules and interfaces.

## Core Duties
- Define the overall system design and component architectures.
- Create and maintain system architecture diagrams following the C4 model.
- Write and publish Architectural Decision Records (ADRs) to document key technical design choices.
- Formulate precise design contracts to establish clean boundaries and interfaces between components.

## Outputs
- Design Contract

<!-- BEST_PRACTICES_APPENDED_START -->

# Hexagonal Architecture Pattern

This document defines the guidelines and constraints for implementing Hexagonal Architecture (Ports and Adapters). This pattern decouples the core business logic from external components, frameworks, and delivery mechanisms.

## Core Layers

1. Core Domain
   - Location: The center of the hexagon.
   - Scope: Contains entities, aggregates, and domain services that implement business rules and use cases.
   - Constraints: Must be isolated. It must not depend on database clients, UI components, HTTP routers, or messaging protocols. It communicates with the outside world solely through Ports.

2. Ports
   - Scope: Interfaces that define structural contracts between the Core Domain and the external world.
   - Incoming (Driving) Ports: Define boundary APIs used by external triggers to interact with the domain (e.g., executing a command or querying state).
   - Outgoing (Driven) Ports: Define contracts that the Core Domain requires from the external environment to perform its tasks (e.g., fetching data, persisting records, or publishing events).

## Adapters

Adapters translate data between external technologies and the formats defined by Ports.

1. Driving (Input) Adapters
   - Scope: Handle external triggers and call Incoming Ports to invoke domain logic.
   - Examples: REST API controllers, CLI command processors, GraphQL resolvers, message queue listeners, and scheduled job runners.
   - Behavior: Receive input data, validate transport-level constraints, translate the payload into domain request models, and execute the matching Incoming Port.

2. Driven (Output) Adapters
   - Scope: Implement the Outgoing Ports defined by the Core Domain to communicate with infrastructure.
   - Examples: Database clients, HTTP outbound gateways, file system clients, SMTP client wrappers, and third-party API clients.
   - Behavior: Invoked by the Core Domain, receive domain models, map them to external infrastructure models, execute the operations, and return translated results back to the core.

## Decoupling Core Logic

- External dependency isolation: The Core Domain must contain zero references to external libraries, framework features, object-relational mapping (ORM) systems, or database systems.
- Technology-agnostic domain: Changing a database, switching from REST to gRPC, or replacing a messaging provider must only require writing a new adapter. The Core Domain code must remain completely untouched.
- Clean interfaces: Ports must be expressed in terms of domain primitives and domain models, never transport-specific or database-specific structures.
