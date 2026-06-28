## Hexagonal architecture (ports and adapters)


This role's design boundary. Keep the core domain clean.

- The core domain holds entities and business rules and imports zero frameworks, ORMs, HTTP clients, or database drivers.
- Driving (incoming) ports define how the outside invokes the domain. Driven (outgoing) ports define what the domain needs from infrastructure.
- Adapters translate: REST controllers, CLI handlers, and queue listeners drive the domain; database clients, HTTP gateways, and file clients implement the outgoing ports.
- Swapping a database, or REST for gRPC, must require only a new adapter. If a domain change is forced by an infrastructure swap, the dependency arrow points the wrong way.
- Ports speak in domain models and primitives, never in transport- or table-shaped structures. This is also why the domain is trivial to unit test: substitute fake adapters.
