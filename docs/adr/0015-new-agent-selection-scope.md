# ADR-0015: Selection scope for dynamically scaffolded agents

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect, software_engineer, product_owner
- Issue: #48

## Context and problem statement

When the capability broker detects a gap that cannot be satisfied by an existing agent or skill, it scaffolds a new agent in `agents/<new>/`. However, for this agent to be usable, it must be selected by `solomon_harness/agent_selection.py` when running on a project. Currently, `agent_selection.py` uses a hardcoded list of `CORE_AGENTS` (always enabled) and stack-gated rules that map technologies to specific specialists. 

We must decide whether dynamically created agents should automatically join the cross-cutting `CORE_AGENTS` list (always enabled) or stay stack-gated, requiring explicit stack signal mapping.

## Decision Drivers

- Lean-fleet principle: avoid loading unused or redundant agents.
- Autonomy and immediacy: a newly created agent should be immediately discoverable and usable.
- Safety: prevent untrusted or poorly-configured scaffolded agents from running automatically across all projects.

## Considered Options

- **Option 1 (CORE by default):** Automatically append newly scaffolded agents to the `CORE_AGENTS` list so they are always enabled on all projects.
- **Option 2 (Stack-gated by default):** Keep newly scaffolded agents stack-gated. They are registered in the index but not enabled unless their stack signals are detected, or they are manually wired into `agent_selection.py`.
- **Option 3 (Hybrid configuration-driven):** Dynamically read each agent's `.agent/config.json` to determine its selection rules (e.g., matching stack signals or marking as cross-cutting/core).

## Decision Outcome

Chosen option: **Option 2 (Stack-gated by default)**. 

To preserve the lean-fleet principle and prevent fleet bloat, dynamically scaffolded agents will stay stack-gated by default. During the scaffolding process in slice C (#48), the agent will be registered in `agents/AGENTS.md` and compiled, but it will not be added to `CORE_AGENTS` automatically. To make it selectable, a corresponding stack signal rule must be added to `solomon_harness/agent_selection.py` or the agent must be manually added to `CORE_AGENTS` if it is cross-cutting.

### Consequences

- **Positive:** Keeps the active fleet lean and targeted to project stacks. Prevents experimental or newly scaffolded agents from running on projects where they are not relevant.
- **Negative:** Newly created agents are not automatically active in the workspace unless a matching stack signal is present or they are manually wired.
- **Follow-ups:** If dynamic/configuration-driven stack mapping is required in the future, we will transition `agent_selection.py` to read rules from `.agent/config.json` (requires a separate ADR).

## More information

This decision is also recorded in the project memory via `save_decision`.
