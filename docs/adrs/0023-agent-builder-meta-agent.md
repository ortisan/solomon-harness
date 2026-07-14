# ADR-0023: agent_builder meta-agent for delegating new-agent construction

- Status: accepted
- Date: 2026-07-05
- Deciders: software_architect, product_owner, practice_curator, software_engineer
- Issue: #49

## Context and problem statement

Currently, the scaffolding of new agents is implemented inline in `practice_curator` (or `broker_agent` in `solomon_harness/curator.py`), causing SOLID/DRY violations and bloating `practice_curator`'s responsibility. The broker should focus on routing and curating, while the builder should focus on constructing/scaffolding.

## Decision drivers

- Separation of concerns and Single Responsibility Principle (SRP).
- Reduction of broker bloat: the capability broker should only route and curate.
- Extensibility and modularity of agent construction logic.

## Considered options

- **Option 1: Inline Scaffolding (Current)**: Keep scaffolding logic inline in `practice_curator`/`broker_agent`.
- **Option 2: Dedicated agent_builder Meta-Agent**: Introduce a dedicated `agent_builder` meta-agent under `agents/agent_builder/` and refactor `practice_curator`/`broker_agent` to delegate agent construction/scaffolding to it.
- **Option 3: Shared Utility Module**: Extract scaffolding logic to a shared Python module in `solomon_harness` without creating a new meta-agent.

## Decision outcome

Chosen option "Option 2: Dedicated agent_builder Meta-Agent", because it aligns with the project's goal of a modular, self-extending fleet where agent-building tasks are first-class agent duties rather than utility scripts, keeping the broker focused solely on curation and routing.

### Consequences

- Positive: Clear separation of concerns; `practice_curator` is simplified; scaffolding and building new agents can be extended/customized within a dedicated builder agent boundary.
- Negative: A new meta-agent directory `agents/agent_builder/` is introduced, slightly increasing the fleet's directory structure complexity.
- Follow-ups: Implement `agents/agent_builder/`, refactor the curator to invoke the builder via standard agent communication or direct delegation, and update tests.

## More information

This decision is also recorded in the project memory via `save_decision`.
