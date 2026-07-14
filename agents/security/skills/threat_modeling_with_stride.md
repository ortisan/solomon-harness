---
name: threat-modeling-with-stride
description: Provides a repeatable STRIDE method for finding design-level flaws before code exists — build the data-flow diagram, mark trust boundaries, enumerate Spoofing, Tampering, Repudiation, Information-disclosure, Denial-of-service, and Elevation-of-privilege threats per element, rank them by CVSS, and mitigate or accept each one. Use when a design change crosses a trust boundary, before implementation starts, or when re-opening an existing threat model after a new data store or listener appears.
---

# Threat Modeling with STRIDE

A repeatable method for finding design-level flaws before code exists: draw the data-flow diagram, mark trust boundaries, enumerate STRIDE threats per element, rank them, and mitigate or formally accept each one. A design change that crosses a trust boundary without a threat model is not ready for implementation.

## Method: the four questions

Structure every session around Shostack's four questions: what are we working on (produce the data-flow diagram); what can go wrong (STRIDE per element); what are we going to do about it (a mitigation or a signed accepted risk per threat); did we do a good job (verify mitigations with tests, revisit on design change). Timebox the first pass to 60-90 minutes per feature — depth comes from iteration, not a marathon session.

## Data-flow diagrams and trust boundaries

Model the system with five element types: external entities (users, host tools, third-party services), processes (your code), data stores (databases, files, caches), data flows (every arrow), and trust boundaries. A trust boundary is any line where the level of trust changes: user input entering the application, a process boundary, a network hop, a container boundary, the line between CI and repository secrets. In this repository the boundaries include: host tool to MCP server (`solomon_harness/mcp_server.py`), application to the SurrealDB/SQLite memory store, harness to the Docker daemon, and CI runner to repository secrets.

Keep the DFD small — one level of decomposition is usually enough. Use Mermaid or OWASP Threat Dragon so the diagram lives in the repo and diffs in review; pytm covers threat-model-as-code when the element list gets large.

## STRIDE per element

Do not brainstorm threats free-form. Walk each DFD element and apply only the categories that fit that element type:

| Element | S | T | R | I | D | E |
| --- | --- | --- | --- | --- | --- | --- |
| External entity | x | | x | | | |
| Process | x | x | x | x | x | x |
| Data store | | x | x | x | x | |
| Data flow | | x | | x | x | |

For each applicable cell, ask the category question and record the threat as a concrete attacker action, not a vague label:

- Spoofing: pretending to be another user, service, or origin. Mitigate with authentication: verified `iss`/`aud` on tokens, mTLS between services, signed webhooks.
- Tampering: modifying data or code in transit or at rest. Mitigate with integrity controls: TLS, MACs and signatures, parameterized writes, strict file permissions.
- Repudiation: denying an action because nothing recorded it. Mitigate with append-only audit logs forwarded off-box.
- Information disclosure: data reaching someone unauthorized. Mitigate with encryption in transit (TLS 1.2 floor, 1.3 preferred) and at rest, access checks on every read, logs stripped of secrets and PII.
- Denial of service: resource exhaustion. Mitigate with rate limits, timeouts, payload caps, bounded retries with backoff.
- Elevation of privilege: gaining rights above one's level. Mitigate with least privilege, deny-by-default authorization at every layer, no dynamic privilege grants.

## Risk ranking

Rank threats so remediation order is defensible. Use CVSS v4.0 (FIRST, November 2023) as the primary scale; accept v3.1 vectors since NVD and most scanners still emit them. Score the base metrics (CVSS-B), then enrich: EPSS estimates exploitation probability over the next 30 days, and CISA KEV presence overrides any mild score upward. Do not use DREAD for new work — Microsoft dropped it because two raters rarely produce the same number. When a design-time threat has no CVSS vector, use a simple likelihood-times-impact matrix (High/Medium/Low on each axis) or the OWASP Risk Rating methodology, and record the rationale next to the score.

A threat with no mitigation and no signed accepted risk blocks the design.

## The threat model is a living document

Store the model next to the code (`docs/` or the feature's ADR), not in a wiki nobody diffs. Re-open it whenever a trust boundary changes: a new external entity, data store, network listener, or deserialization point. Each mitigation maps to a test or control CI can check; each accepted risk carries an owner and expiry. Persist decisions with `save_decision` and link them to the issue with `log_issue` so `/solomon-review` can verify them at the gate.

## Worked mini-example: the MCP memory server

Elements: host tool (external entity), MCP server process, SurrealDB container (data store), the stdio flow between tool and server, the WebSocket flow to SurrealDB.

- Spoofing (process): any local process can register a look-alike MCP server; the host trusts the command path in `.mcp.json`. Mitigation: config files owned by the user, no PATH-relative commands.
- Tampering (data store): SurrealDB listens on a localhost port with default root credentials; another local process can rewrite memory rows. Mitigation: credentials from env, bind to 127.0.0.1 only, residual risk documented for shared machines.
- Repudiation (process): memory writes carry no actor identity. Mitigation: session id and timestamp on every write.
- Information disclosure (flow): decisions and handoffs may contain repo-private detail; the SQLite fallback file inherits default permissions. Mitigation: mode 0600 on the fallback file, no secrets in memory rows.
- Denial of service (data store): an unbounded `get_open_issues` scan can stall the session hook. Mitigation: query limits and client timeouts.
- Elevation of privilege (process): an MCP tool that interpolated caller text into SurrealQL would let a prompt escalate to arbitrary queries. Mitigation: bound parameters only — verified by a test.

This table, ranked and with owners, is the entire deliverable for a change of this size.

## Common pitfalls

- Enumerating threats without a DFD, which produces a generic checklist instead of threats tied to real elements and boundaries.
- Applying all six STRIDE categories to every element; data flows do not spoof and external entities do not elevate — the noise buries real findings.
- DREAD scores presented as objective numbers; the scores are opinions, and a reviewer should reject any ranking without stated rationale.
- A model written once and never re-opened, so a new listener or deserialization point ships unmodeled.
- Mitigations that are adjectives ("hardened", "validated") instead of controls a test can verify.
- Accepted risks with no owner or expiry, which become silent permanent exceptions.
- Modeling only the product surface and skipping CI, build, and operational tooling, where the credentials usually live.

## Definition of done

- [ ] DFD exists with external entities, processes, data stores, flows, and explicit trust boundaries, committed to the repo.
- [ ] Every element walked against the STRIDE-per-element mapping; each threat states a concrete attacker action.
- [ ] Every threat ranked: CVSS v4.0 or v3.1 vector where one applies, documented likelihood-impact rationale otherwise, EPSS/KEV checked for known CVEs.
- [ ] Every threat has a mitigation mapped to a verifiable control or test, or a signed accepted risk with owner and expiry.
- [ ] Decisions persisted via `save_decision` and referenced from PLAN.md and the issue.
- [ ] A re-open trigger is stated: which design changes invalidate this model.
- [ ] Mitigation tests exist and fail when the control is removed.
