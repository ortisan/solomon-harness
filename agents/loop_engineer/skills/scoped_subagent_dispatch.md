---
name: scoped-subagent-dispatch
description: Governs the contract for fanning bounded work out to parallel subagents from a parent driver, as /solomon-scan-arch, /solomon-scan-dedup, and multi-specialist audits do — a mandatory parent-led read-only scout before any dispatch, non-overlapping and independently-answerable slices sized to what the scout actually found, a scoped-write contract naming exactly one output artifact per dispatched agent with no edits outside it, a no-fabrication rule when a slice fails, and a hard parallelism cap. Use when planning or reviewing a fan-out to parallel Agent/Task-tool subagents, writing a new scan or audit loop, or diagnosing a dispatch that produced overlapping, fabricated, or unbounded results.
---

# Scoped Subagent Dispatch

This skill governs the contract for fanning bounded work out to parallel subagents from a parent driver — the pattern behind `/solomon-scan-arch`, `/solomon-scan-dedup`, and the multi-specialist audits this project runs when one question spans more territory than a single context should carry. It is written against the host's native Agent/Task tool rather than any specific vendor's CLI mechanics, because the point of writing it here is portability: the same rule holds whether the parent driver is Claude Code's Task tool, Codex's subagent primitive, or Gemini's equivalent. Keeping the contract at this level of abstraction is what makes it an auditable project rule instead of one host's implementation detail.

## Mandatory parent-led scout

Before any dispatch, the parent driver performs a brief, bounded, read-only recon of the problem space itself — a handful of targeted `Grep`/`Glob`/`Read` calls, not a deep dive. The scout's job is to learn the territory well enough to slice it correctly; it does not produce the analysis or the fix itself, and it does not run long. This is the load-bearing step: skipping it is what turns a parallel dispatch into wasted spend, because two agents sent into overlapping or already-answered territory without a prior scout will read the same primary files under different pretexts and return duplicate or contradictory findings for the same token budget. A parent that dispatches first and discovers the territory's actual shape from the results back is running the scout after the fact, at full dispatch cost, instead of before it, at recon cost.

## Non-overlapping, independently-answerable slices

The scout's output must partition the work into slices that satisfy two conditions. First, non-overlapping: no two slices should need to read the same primary files for the same purpose — if two slices both require deep familiarity with the same module, that is one slice, not two. Second, independently answerable: a slice's output must not depend on another slice's output, because dispatched agents run in parallel with no mid-flight coordination channel between them; a slice that needs another slice's finding first is a sequencing problem disguised as a parallel one.

When the scout turns up fewer genuinely distinct slices than the number of agents available, dispatch fewer and say so. Do not pad the slice count to hit a target headcount — a padded slice either silently overlaps a neighbor's territory or asks a question too thin to answer on its own, and either failure wastes a dispatch slot without adding signal. Reducing the count is the correct response to a scout that found less structure than expected, not a sign the scout was insufficient.

## The scoped-write contract

Every dispatched agent gets exactly one named output artifact — a specific file path it is to write, or, for a fork, a single well-defined return payload the parent will read from the completion notification — and no standing to touch anything else. The parent's dispatch prompt must name three things before the call is made: the slice's exact scope and boundary, an identifier for the slice, and the exact output the dispatched agent is expected to produce. If any of the three is missing or ambiguous, that is a scope defect in the parent's own planning to fix before dispatching, not something the dispatched agent should be left to infer.

No edits outside the named output: a research or audit slice does not get to modify existing files, run mutating commands, or write to any path beyond what the parent named, unless that edit is literally the one task assigned — a `software_engineer` subagent tasked with a bounded code change still writes only inside the diff its own prompt scoped, nothing adjacent "while it's in there."

Map the host tool's own primitives onto this contract rather than replacing it. A fork inherits the parent's full context and is the right choice when the intermediate output is not worth carrying forward into the parent's own context directly — it is cheaper because it shares the parent's cache, but it still gets exactly one scope and one expected output like any other dispatch. A fresh, non-fork agent inherits nothing, so its prompt must restate the scope and the full contract as if briefing a colleague who just walked in with no memory of this conversation — terse, tool-shaped instructions to a fresh agent produce shallow, generic work, because the agent has no way to fill the gaps from context it does not have.

Two disciplines apply once a dispatch is in flight and not yet resolved. Never peek at a fork's in-progress transcript to shortcut the wait — pulling a fork's intermediate tool noise into the parent's own context defeats the reason the work was forked out in the first place. And never fabricate, predict, or narrate a dispatched agent's result before its completion notification actually arrives, in any format — prose, a fabricated summary, or a structured guess. The notification is an event that arrives later, from outside the parent's own reasoning; treating it as something the parent can pre-write is the dispatch-level version of the ghost-action problem: a result reported before the work that would produce it has actually finished.

## No fabrication on failure

When a dispatched agent's slice fails outright, times out, returns empty, or is caught violating its named scope, the parent's obligation is to re-dispatch that slice or explicitly mark it uncovered in the final synthesis — never to author the missing content itself and present the result as if the slice had produced it. An audit or scan that silently backfills a missing slice's findings is indistinguishable, from outside the parent's own reasoning, from one that never ran that slice at all, and the gap it papered over resurfaces later as a false completeness claim nobody can trace back to its source.

A scope violation is treated with the same severity as a hard failure, not as a minor note: a slice that wrote outside its named output, edited a file it was never asked to touch, or ran a command its task never authorized has its output rejected outright. Stop, do not accept or merge that output into the parent's synthesis, and re-dispatch with the scope restated — tighter, if the ambiguity in the original prompt is what caused the drift.

## A hard parallelism cap

Cap concurrent dispatches at a small, fixed, single-digit ceiling regardless of how many slices the scout could in principle support. This harness already applies the same order-of-magnitude discipline to bounded fan-out elsewhere in the codebase — `MAX_FANOUT_WORKERS = 8` bounds the cross-tenant read fan-out in `solomon_harness/cockpit_read.py` for exactly this reason: an unbounded fan-out degrades from a supervised set of parallel workers into an unreviewable swarm, whether the units of work are I/O reads or subagent dispatches. Treat the cap as a ceiling, never a target — dispatch the number of genuinely non-overlapping slices the scout actually found, up to the ceiling, and stop there rather than manufacturing enough slices to fill it.

## Why this lives in project rules, not host mechanics

A rule expressed in terms of one vendor's CLI flags only works where that binary and its registry exist. A rule expressed as "one scout, N non-overlapping scoped-write slices, no fabrication, a hard cap" holds regardless of which host tool executes the fan-out. Keeping the contract at this level is what lets an audit pattern or a scan loop written once travel to a Codex or Gemini host without a rewrite, and what makes the rule something a reviewer can audit against as a project standard rather than trust as one tool's undocumented behavior.

## Common pitfalls

- Dispatching before scouting, discovering the actual territory shape from overlapping or contradictory results instead of from a cheap recon pass.
- Padding the slice count to match a requested number of agents instead of reducing it when the scout found less independent structure.
- Leaving the scope, identifier, or expected output unstated in a dispatch prompt and letting the dispatched agent guess at any of the three.
- Letting a dispatched agent's edits spill outside its one named output "since it was already in that file."
- Peeking at a fork's in-flight transcript, or narrating what a still-running dispatch will report, instead of waiting for its actual completion notification.
- Silently authoring a failed slice's missing content so the round looks complete, instead of re-dispatching or marking it uncovered.
- Treating a scope violation as a minor note rather than rejecting the output and re-dispatching.
- Sizing a dispatch round to an arbitrary large number instead of the fixed single-digit cap this harness already applies to comparable fan-out.

## Definition of done

- [ ] A parent-led read-only scout ran before any dispatch, and the slice boundaries trace to what it found.
- [ ] Every dispatched slice is non-overlapping with every other slice and answerable without depending on another slice's output.
- [ ] The slice count was reduced, with the reduction noted, rather than padded to match a requested headcount.
- [ ] Every dispatch prompt names the slice's scope, its identifier, and its exact expected output before the call is made.
- [ ] No dispatched agent wrote or ran anything outside its one named output.
- [ ] No fork's in-flight transcript was peeked at, and no dispatched result was narrated or fabricated ahead of its actual completion notification.
- [ ] A failed or scope-violating slice was re-dispatched or marked uncovered in the synthesis — never silently backfilled by the parent.
- [ ] Concurrent dispatches stayed within a fixed single-digit cap for the round.
