# QA Specialist Profile

The QA Specialist designs test automation strategy, executes verification reviews, and conducts user acceptance testing to ensure reliability.

## Core Duties
- Design, write, and execute automated tests, including unit, integration, end-to-end (E2E), and backtest tests.
- Perform structured verification reviews of code changes and release candidates.
- Run tests and execute verification steps on the designated branches (e.g. validating feature/* changes against develop, and verifying release/* candidate branches prior to production deployment).
- Plan and coordinate User Acceptance Testing (UAT) phases.
- Compile and publish detailed QA execution and verification reports.

## Outputs
- QA Report

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

# Secure Development Pattern

This document defines the guidelines and security practices to ensure code resilience, prevent vulnerabilities, and mitigate system exploits.

## Threat Modeling: The STRIDE Framework

Apply the STRIDE framework during the design and planning phase of every feature. Identify and document potential threats in the following categories:

1. Spoofing
   - Threat: An attacker acts as another user or system entity.
   - Mitigation: Enforce robust authentication mechanisms, secure session tokens, and cryptographic verification of service identities.

2. Tampering
   - Threat: Unauthorized modification of data, configurations, or system binaries.
   - Mitigation: Implement message authentication codes (MACs), digital signatures, strict filesystem permissions, and write-once storage rules where applicable.

3. Repudiation
   - Threat: A user denies performing an action due to a lack of evidence or logging.
   - Mitigation: Implement immutable audit logs, verify transactions with digital signatures, and establish secure log forwarding policies.

4. Information Disclosure
   - Threat: Unauthorized users gain access to sensitive or private data.
   - Mitigation: Encrypt data at rest and in transit, apply access control verification, mask sensitive records, and restrict logs to non-sensitive payloads.

5. Denial of Service (DoS)
   - Threat: Exhausting system resources to make the service unavailable.
   - Mitigation: Implement rate-limiting rules, enforce execution timeouts, validate payload size constraints, and manage request timeouts at boundary gateways.

6. Elevation of Privilege
   - Threat: An attacker gains permissions higher than their authorization level.
   - Mitigation: Apply the principle of least privilege, enforce role-based access control (RBAC) at every endpoint, and avoid dynamic privilege assignments.

## Secure Coding Practices

1. Input Sanitization and Schema Validation
   - Never trust input from external clients, network endpoints, or database fields.
   - Validate all payloads against strict schemas before processing.
   - Sanitize text values to remove markup or script tags before outputting them to web clients or files.

2. Parameterized Queries
   - Construct database queries using parameterized values or raw prepared statements.
   - Never construct queries by concatenating raw strings with user input, as this practice causes SQL injection vulnerabilities.

3. Dependency Scanning
   - Scan all third-party libraries and modules for known security vulnerabilities continuously during build cycles.
   - Pins all dependency versions and review updates systematically to avoid supply chain exploits.

4. Cryptographic Isolation
   - Store sensitive keys, API credentials, and database passwords in isolated environment variables or dedicated secret management systems.
   - Never hardcode credentials in code repositories or commit them to git history.
   - Keep keys isolated from application logic, rotating them on a set schedule.

5. Stripped Error Disclosures
   - Strip stack traces, internal system details, hostnames, and database architectures from external error messages.
   - Return generic error messages to external callers, saving detailed logs containing debugging context in secure, internal logging systems.
