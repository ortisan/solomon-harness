# Documentation Best Practices

Standards for producing technical and business documentation, user guides, API/developer docs, and design records that stay accurate, findable, and maintainable.

## Operating principles

- Docs-as-code: source docs in the repo next to the code they describe, in Markdown or reStructuredText. Every change ships through a branch, a PR, and review. No doc lives only in a wiki UI or a shared drive.
- Write for one reader and one job per page. State the audience and the task in the first two sentences. If a page serves two audiences, split it.
- Front-load the answer (inverted pyramid). Put the conclusion, the command, or the decision first; put rationale and edge cases after.
- Single-source facts. A value, limit, or endpoint is defined in exactly one place and included or linked elsewhere. Duplicated facts drift.
- Minimum viable documentation: a short, correct page beats a long, stale one. Delete content you cannot keep current.

## Structure: classify by Diátaxis

Every page is exactly one of these four types. Mixing them is the most common documentation defect. Do not blend a tutorial with reference material.

- Tutorial: learning-oriented, a guided lesson that always succeeds for a beginner. Concrete, no choices, no alternatives.
- How-to guide: task-oriented, a recipe to solve one real problem. Starts from a goal, assumes competence.
- Reference: information-oriented, dry and exhaustive (API endpoints, config keys, CLI flags). Describes, never teaches.
- Explanation: understanding-oriented, the "why" — design rationale, trade-offs, background.

Name and locate pages so the type is obvious. A reader on a deadline must reach the right page in two clicks.

## Page-level standards

- Title is a noun phrase (reference/explanation) or a task in imperative or gerund form (how-to: "Rotate API keys", "Configuring TLS").
- Every page carries front matter metadata: `owner`, `status` (draft/reviewed/deprecated), `last_reviewed` (ISO date), and the product version or commit it was validated against.
- One H1 per page. Heading depth no greater than H4. Sections short enough to scan.
- Procedures are numbered steps, one action per step, with the expected result stated after steps that produce visible output.
- Every command and code block is copy-pasteable and tested. Show real, runnable examples, not `<placeholder>` soup; when placeholders are unavoidable, define each one immediately below the block.
- Use semantic line breaks (one sentence or clause per line) in source. It keeps diffs reviewable and review comments precise.
- Provide alt text for every image and diagram. Store diagram source (Mermaid, PlantUML, or Structurizr DSL), not only the exported PNG, so diagrams are diffable and editable.

## Readability and style

- Follow one style guide and enforce it: Google developer documentation style guide or the Microsoft Writing Style Guide. Pick one per project and do not mix.
- Target US grade 8 to 10 readability (Flesch-Kincaid). Average sentence under 25 words. Prefer active voice and present tense ("the service returns", not "the service will return").
- Second person ("you") for instructions. Define every acronym on first use. Maintain a project glossary and link to it.
- Lint prose in CI: Vale with a style package (Google/Microsoft), plus `markdownlint` for structure. Run `lychee` or `markdown-link-check` to fail the build on broken links.
- Honor the project humanizer rules: direct, concise, senior-engineer tone. No emojis or icons. Ban the cliches listed in the workspace rules (delve, leverage, testament, dive into, feel free, in summary, moreover, firstly, secondly, lastly). Add them to the Vale vocabulary as errors.

## API and developer documentation

- Reference is generated from a machine-readable contract, not hand-written. Maintain an OpenAPI 3.1 spec (or AsyncAPI for event APIs) as the source of truth; render with Redoc, Swagger UI, or Stoplight Elements. Lint the spec with Spectral in CI.
- Every endpoint documents: purpose, auth/scopes required, all parameters with types and constraints, request body schema, every response status with body schema, error codes with causes and fixes, rate limits, idempotency, and pagination.
- Provide at least one complete request/response example per endpoint, including a failure example. Examples must match the current schema; validate them against the spec.
- Document authentication end to end once (obtaining credentials, sending them, refreshing, scopes) and link endpoints to it.
- Provide a quickstart that gets a developer to a first successful call in under 15 minutes, and SDK snippets in the languages your users actually use.
- Version the API docs with the API. Keep a changelog and a deprecation policy that states timelines and migration steps. Signal pending removal on the wire with the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) response headers and document the dates; never silently remove an endpoint from the reference.

## Design documentation and architecture records

- Record significant decisions as Architecture Decision Records (ADRs) using the MADR template: context, decision, status, consequences, alternatives considered. One decision per ADR, immutable once accepted; supersede rather than rewrite.
- Use the C4 model for architecture diagrams (Context, Container, Component; Code only when it earns its keep). Keep each level on its own page. Maintain diagrams as code (Structurizr DSL or Mermaid) so they regenerate.
- Design docs state the problem, constraints, non-goals, the chosen approach, rejected options with reasons, and open questions. Link the design doc to the issues and PRs that implement it.
- System architecture records name the design contracts (interfaces and invariants) that bound each component, consistent with the SOLID and modularity rules the engineering specialists follow.

## Operational docs: runbooks and user guides

- Runbooks are written for an on-call engineer at 3 a.m.: alert/symptom, business impact and severity, diagnosis steps, remediation commands, rollback procedure, and escalation contacts. Every step is copy-pasteable and tested in a drill.
- User guides are task-organized, not feature-organized. Lead with what the user wants to accomplish. Include prerequisites, a verification step, and a troubleshooting section for the top failures.
- Changelogs follow Keep a Changelog and Semantic Versioning. Group entries under Added, Changed, Deprecated, Removed, Fixed, Security. Write entries for users, not commit-by-commit.

## Documenting specialist artifacts accurately

When you document another specialist's work, capture the mandatory fields that role is required to produce. Missing fields make the doc non-compliant.

- Quant trading strategy / Model Hypothesis: record target Sharpe ratio, drawdown limit, profit factor, latency and slippage constraints, the dataset and features used, and the network or model architecture. A strategy doc without all of these is incomplete.
- ML / DRL work: record the validation method (cross-validation and out-of-sample test design), the explicit zero-data-leakage controls, and the safety guards (tensor-shape validation before critical ops, division-by-zero and float-overflow checks). State which guards exist, not just that the model works.
- QA artifacts: document that all external API calls and services are mocked, the unit and integration coverage for the change, and the specific backtesting-logic tests and their parameters.
- Security artifacts: document threat models by STRIDE category (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege), the SAST and dependency/vulnerability scan results, and the mitigation for each finding.
- Software engineering artifacts: document the TDD evidence (Red-Green-Refactor), the SOLID/modularity decisions, and the design contracts between components; preserve existing docstrings and comments unrelated to the change.
- Business value and product artifacts: state the user or business problem, the measurable outcome, the baseline and target metric that proves it, and the owner accountable for the result. Keep one phrasing of value per artifact so it reads the same to engineering and to the business.

## Maintainability and lifecycle

- Assign an owner to every page. Unowned docs rot.
- Review cadence: re-validate each page at least every 90 days; flag any page past 180 days since `last_reviewed` as stale and block it from the "current" navigation.
- Tie docs to the workflow lifecycle: documentation is part of Release and Documentation, synced with `scripts/wiki-sync.sh`; a release is not done until its docs and changelog are updated.
- Treat a doc bug like a code bug: file an issue, fix at the source, verify the link/example, and close. Do not patch symptoms in a downstream copy.
- Persist documentation decisions and structure changes to project memory (decisions, handoffs) so the next agent inherits the rationale.

## Common pitfalls

- Tutorials that branch into options and become unfollowable. Keep them linear and guaranteed to succeed.
- Reference written by hand and drifting from the API. Generate it from the spec.
- Screenshots of fast-changing UI with no source and no alt text. Prefer text and diagrams-as-code; automate screenshots where you must use them.
- "Latest"-only docs with no version pinning, so a user on an older release follows wrong steps.
- Duplicated config tables in five pages. Single-source and include.
- Marketing tone, hedging, and filler. Say what the system does and what the reader must do.

## Definition of done

- [ ] Page is classified as exactly one Diátaxis type and placed/named accordingly.
- [ ] Audience and task stated up front; answer front-loaded.
- [ ] Front matter present: owner, status, `last_reviewed`, validated version/commit.
- [ ] All commands and code blocks tested and copy-pasteable; placeholders defined.
- [ ] API reference generated from a Spectral-linted OpenAPI 3.1 spec; every endpoint covers auth, params, responses, errors, rate limits, and has a success and a failure example.
- [ ] Diagrams stored as source (Mermaid/PlantUML/Structurizr); every image has alt text.
- [ ] Decisions captured as MADR ADRs; design docs list non-goals and rejected options.
- [ ] Specialist artifacts include their mandatory fields (quant metrics, ML validation/guards, QA mocking, STRIDE).
- [ ] Vale, markdownlint, and link checking pass in CI; no banned cliches, no emojis.
- [ ] Readability within grade 8 to 10; active voice; glossary updated for new terms.
- [ ] Changelog and version updated; wiki synced via `scripts/wiki-sync.sh`.
