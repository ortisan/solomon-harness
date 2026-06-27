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
