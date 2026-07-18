---
name: capability-broker
description: Governs how the practice_curator routes a free-text demand to the best-fit existing agent or reports a structured capability gap (adapt_skill or create_agent), per the verdict contract fixed in ADR-0008 and capability_router.py. Use when resolving an incoming task demand to an agent, or when no agent covers it and a skill adaptation or new-agent scaffold must be proposed.
---

# Capability Broker

Governs how the practice_curator acts as a proxy for incoming demands: resolve a free-text demand to the best-fit existing agent, or report a structured capability gap, and on a gap drive a human-gated acquisition. Routing and gap detection are read-only and deterministic. An external skill adaptation uses a reviewed draft PR; a new agent is registered directly in the installed harness catalog without changing the consumer project's Git history. This skill fixes the contract recorded in ADR-0008 and amended by ADR-0040.

## The verdict contract

`route(demand, matcher)` (see `solomon_harness/capability_router.py`) returns one of two verdicts:

- **route** — an existing agent serves the demand: `agent`, a single-line `rationale`, and ranked `alternatives` (surface them as enumerated options with an "Other" escape hatch; never silently collapse ambiguity to one pick).
- **gap** — no agent fully covers it: `missing_capability`, `nearest_agent` (or null), and `suggested_action`:
  - `adapt_skill` when a `nearest_agent` exists that only lacks a skill — fetch and adapt an external skill into that agent (slice #47).
  - `create_agent` when no agent fits — scaffold a new agent (slice #48), delegated to the `agent_builder` meta-agent.

The gap verdict is the hand-off shape the acquisition slices consume; do not widen it without updating ADR-0008 (recorded in MADR 4.0 format under `docs/adrs/`).

## The match is an injected port

The demand→agent match is supplied by the host LLM (the harness's model), passed in as a callable matcher port (`matcher(demand, catalog) -> Match`, Python 3.10+); in tests it is a deterministic stub. The router core itself opens no network socket and instantiates no ML model — it only loads the catalog read-only (each `agents/<name>/agents/<name>.md` role file, discovered via `agent_selection.discover_agents`) and builds the verdict. Do not add an embedded classifier; an ML matcher would need its own ADR.

## Read-only routing and human-gated acquisition

- Slice A (routing/gap) mutates nothing under `agents/`; it fails closed (raises) on an empty or unreadable catalog rather than guessing.
- Interception is orchestration-time, not runtime: a newly adapted or created agent is invocable only after `compile` + a session restart.
- `create_agent` requires a valid installed manifest, writes only below `.agents/solomon/agents/<name>`, recompiles the Claude, AGY, and Codex adapters, records a best-effort memory decision, and returns `mode: direct_registration` with `agent_path` and `restart_required: true`. It creates no branch, commit, pull request, or PR handoff, and it does not rewrite the package-owned `.agents/solomon/AGENTS.md`.
- `adapt_skill` retains the reviewed-PR path: external sources are allowlisted in `skill-sources.json`, fetches are pinned, fetched content is untrusted data that is never executed, and the security agent reviews the single-agent draft PR before merge.
- Autonomy ceiling: both acquisitions remain behind the interactive human gate. The broker never merges. Headless and autonomous stages report the gap but cannot apply either action.

## Common pitfalls

- Collapsing an ambiguous match to a single agent and discarding the alternatives — the user loses the choice; always carry `alternatives` and present them as enumerated options.
- Returning a "route" to an agent that is not in the catalog — a matcher contract violation; the core rejects it (fails closed) rather than routing to a non-existent agent.
- Treating a missing-skill case as a brand-new agent — if a `nearest_agent` covers the domain, the action is `adapt_skill`, not `create_agent`.
- Letting the matcher reach into the network or a model from inside the core — keep the match behind the injected port so the core stays deterministic and testable.
- Sending `create_agent` through the reviewed-PR path — this changes the consumer repository for a harness-local registration and violates ADR-0040.
- Applying `adapt_skill` without a human-approved single-agent draft PR — external content still requires the reviewed path and security verdict.

## Definition of done

- [ ] A demand resolves to a `route` or a `gap` verdict via the injected matcher, with no file mutation and no network/model call in the core.
- [ ] Ambiguity surfaces ranked `alternatives`; a route to an unknown agent and an empty catalog both fail closed.
- [ ] A gap names the `missing_capability` and the correct `suggested_action` (`adapt_skill` with a `nearest_agent`, else `create_agent`).
- [ ] The contract here matches ADR-0008 and the `route()`/verdict shapes in `capability_router.py`.
- [ ] `create_agent` registers once below `.agents/solomon/agents`, compiles all host adapters, leaves Git and GitHub untouched, and reports that a session restart is required.
- [ ] `adapt_skill` opens a human-approved single-agent draft PR and never merges autonomously.
