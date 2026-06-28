## C4 model diagrams


C4 names four levels after four C's: Context, Containers, Components, Code. Model at these four zoom levels and stop there. Do not invent extra levels.

1. **Level 1 - System Context** — the system as one box, surrounded by users (personas) and external systems. Audience: everyone, including non-technical stakeholders. One per system.
2. **Level 2 - Container** — deployable/runnable units inside the system boundary: services, SPAs, mobile apps, databases, message brokers, serverless functions. Each container shows technology choice and the protocol of every link (HTTPS/JSON, gRPC, AMQP, JDBC). This is the most useful level; spend the most effort here.
3. **Level 3 - Component** — the major structural building blocks inside one container and their responsibilities. Draw it only for containers with real internal complexity; skip it for thin or generated ones.
4. **Level 4 - Code** — class/ER detail. Generate it from code (IDE, tooling) rather than drawing by hand; hand-drawn code diagrams rot within a sprint.

Rules that keep diagrams honest:

- Every element has a name, a type, and a one-line responsibility. Every relationship has a verb-phrase label and a direction ("Sends order events to", not a bare arrow).
- Every dependency arrow names its protocol and synchronicity (sync request/response vs async event). An unlabeled arrow is a defect.
- One diagram answers one question. If a Container diagram needs a legend longer than five entries, split it.
- Keep diagrams as text-based, version-controlled artifacts: **Structurizr DSL**, **Mermaid C4**, or **PlantUML with C4-PlantUML**. Diagrams live in the repo next to the code and change in the same PR. Binary exports from drawing tools are not the source of truth.
- Include a legend, a "last updated" date, and the author. A diagram with no date is assumed stale.
- Notation discipline: solid line for synchronous calls, dashed for asynchronous/events; consistent shapes per element type across all diagrams.

Common pitfalls: mixing abstraction levels in one diagram (a class sitting next to a load balancer); drawing the org chart instead of the runtime; omitting the data stores; drawing the aspirational system without marking what does not exist yet. Mark planned elements explicitly (for example a "PLANNED" tag) so readers do not mistake intent for reality.
