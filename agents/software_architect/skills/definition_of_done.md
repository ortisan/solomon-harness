# Software Architect Definition of Done

The exit checklist for software-architect deliverables: C4 diagrams, ADRs, design contracts, NFR scenarios, and boundary reviews. Architecture work counts as done only when every item below holds; the pitfalls list the usual ways the checklist gets ticked without the substance behind it.

## Common pitfalls

- An ADR checked off without a Status, a Date, or two genuinely considered options — a single-option record is a rationalization of a choice already made, so the "two options considered" item is unmet.
- A Consequences section listing only benefits — the real cost was never found, which fails the "including the cost" clause and hides the trade-off from the next maintainer.
- Context or Container diagrams committed as binary exports or without a last-updated date — they cannot be diffed in the PR and are presumed stale, failing the "version-controlled text, dated" item.
- Code structure changed without the Container view updated in the same PR — the diagram now describes a system that no longer exists, so every item ticked against it is fiction.
- A boundary contract missing its closed error set, idempotency statement, or QoS terms — callers cannot enumerate failures or retry safely, so the failure-mode half of the contract item is absent.
- A prose-only contract with no OpenAPI/Protobuf/AsyncAPI schema and no consumer-driven contract test — producer and consumer drift silently between releases, leaving the "checkable schema" item unenforced.
- An NFR recorded as an adjective ("fast", "scalable") instead of a six-part scenario with a number — it maps to no SLI, test, or dashboard, so the measurable-scenario item cannot be verified.

## Definition of done


- [ ] Context and Container diagrams exist as version-controlled text (Structurizr/Mermaid/PlantUML), dated, with every arrow labeled by protocol and synchronicity.
- [ ] Component diagrams exist for every container with real internal complexity; code-level diagrams are generated, not hand-drawn.
- [ ] Each non-reversible decision has an ADR with Status, Context, Decision, Consequences (including the cost), and at least two options considered.
- [ ] Superseded ADRs are linked, not edited; no accepted ADR was altered in substance.
- [ ] Every component boundary has a written contract: signature, pre/postconditions, invariants, closed error set, idempotency, and QoS terms, expressed in domain types with no transport or persistence leakage.
- [ ] Contracts are encoded in a checkable schema (OpenAPI/Protobuf/AsyncAPI) and backed by consumer-driven contract tests.
- [ ] Every significant NFR is a six-part measurable scenario with a number, mapped to the mechanism that satisfies it and the SLI/test/dashboard that proves it.
- [ ] SOLID reviewed at each boundary; CI fitness functions enforce dependency direction and forbid cycles and layer violations.
- [ ] STRIDE pass completed on each trust boundary with mitigations recorded; no open high-severity threat.
- [ ] Role-specific guards present where relevant: TDD-friendly seams, mocked externals, ML leakage/shape/overflow guards, quant Sharpe/drawdown/profit-factor/latency/slippage targets stated.
- [ ] All artifacts pass the humanizer check: no emojis, no banned cliches, senior-engineer tone.
