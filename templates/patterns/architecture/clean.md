# Clean Architecture Pattern

This document defines the guidelines and constraints for implementing Clean Architecture. Clean Architecture separates software design into logical layers to isolate the core domain from external changes and framework details.

## Layer Boundaries

The system is structured into four main concentric layers:

1. Entities
   - Location: Core layer.
   - Scope: Encapsulates enterprise-wide or core business rules, domain objects, and validation rules.
   - Constraints: Must not import or reference any component outside this layer. Changes to external databases, web APIs, or user interfaces must not impact this layer.

2. Use Cases
   - Location: Application logic layer.
   - Scope: Orchestrates the flow of data to and from entities. Implements system use cases and business scenarios.
   - Constraints: References entities directly, but knows nothing about database technologies, web services, or UI components. Defines input and output interfaces (ports) to communicate with outer layers.

3. Interface Adapters
   - Location: Gateway, controller, and presenter layer.
   - Scope: Converts data between the format most convenient for use cases/entities and the format most convenient for external agencies (e.g., databases, web pages).
   - Examples: Controllers, presenters, database repositories, gatekeepers.
   - Constraints: Implements interfaces defined in the Use Cases layer. Adapts external data formats to domain structures.

4. Frameworks and Drivers
   - Location: Outermost layer.
   - Scope: Built from external tools such as databases, web frameworks, user interface libraries, and device drivers.
   - Constraints: Generally contains only configuration or bootstrap code that connects outer tools to interface adapters.

## The Dependency Rule

Dependencies must only point inwards. A source code dependency must only reference components in a more central layer. 
- High-level policies must not depend on low-level details.
- The Entities layer is the most stable and high-level policy and must have zero outer references.
- No code in an inner circle can mention the name of something that is declared in an outer circle, including databases, UI components, libraries, frameworks, or serialization formats.

## SOLID Principles Guidelines

- Single Responsibility Principle (SRP): A class or module must have one, and only one, reason to change. Separate business rules from representation and data retrieval.
- Open/Closed Principle (OCP): Software artifacts must be open for extension but closed for modification. Implement behavior extensions by adding new code and components rather than editing existing files.
- Liskov Substitution Principle (LSP): Subtypes must be substitutable for their base types. Consumers of interface contracts must function correctly regardless of which adapter implementation is injected.
- Interface Segregation Principle (ISP): Clients must not be forced to depend on interfaces they do not use. Keep interface definitions small, cohesive, and specific to the consumer.
- Dependency Inversion Principle (DIP): High-level modules must not depend on low-level modules; both must depend on abstractions. Abstractions must not depend on details; details must depend on abstractions. Use dependency injection to supply low-level implementations to high-level use cases.
