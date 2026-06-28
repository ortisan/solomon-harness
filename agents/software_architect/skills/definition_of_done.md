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
