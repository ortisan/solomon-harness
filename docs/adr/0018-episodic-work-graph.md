# ADR-0018: Episodic work graph: worked_on edges and graph-based resume

- Status: accepted
- Date: 2026-07-04
- Deciders: software_architect, software_engineer, dba
- Issue: #167

## Context and problem statement

The resume path guesses. `get_latest_activity` returns a single
session-or-handoff row, and `digest.py` recovers the issue being worked by
regexing `#(\d+)` out of the session's free-text `task` string — a heuristic
that breaks the moment a task description omits the number or mentions two.
Sessions and loop runs carry no typed link to the issues they advance, so the
memory cannot answer "what happened last, per issue" without parsing prose
(2026-07-04 memory-architecture review, finding F3). Wave 1 (ADR-0016, #180)
closed the durability funnel over graph edges, so an episodic edge written
during an outage now survives to reconcile — the precondition this wave was
deferred on.

## Decision drivers

- Resume must be a query over typed links, not a regex over prose.
- The edge write has to ride the existing mirrored relate funnel (ADR-0016 F5):
  no second durability mechanism.
- The SQLite fallback must stay a working resume path (parity, as wave 1 did
  for transitions and metrics).
- Consumers pin `get_latest_activity`'s return shape; it cannot change.

## Considered options

- A `worked_on` RELATION edge from episodic rows (sessions, loop_runs) to
  issues, plus a graph resume query (chosen).
- Keep the free-text regex and harden it (more patterns) — still a guess.
- A plain `issue_id` column on sessions — loses the many-issues case and the
  graph traversals the store already supports (ADR-0011).

## Decision outcome

### The worked_on edge

`worked_on` is a `TYPE RELATION` table (own statement in the schema bootstrap,
preserving the one-statement-per-call invariant). Two sources, one target:

- `sessions:<id> -> worked_on -> issues:<github_id>` — `save_session` gains an
  optional `issues` parameter (GitHub issue numbers); after the session row
  lands, one edge per number is written through the wave-1 mirrored relate
  funnel. An issue with no memory row is first created minimally via the
  existing `log_issue` path, so an edge never dangles.
- `loop_runs:<id> -> worked_on -> issues:<github_id>` — `save_loop_run` gains
  an optional `target_issue` (int), stored on the row and edged the same way.
  `workflows._record_loop_run` passes the first purely-numeric stage argument
  (per-issue loop workers and the start/review/release stages carry one); it
  never regexes prose.

On the SQLite fallback (and while degraded), a parity link table `worked_on`
(`source_table`, `source_id`, `github_id`) is maintained so graph-based resume
works without the primary — the same expand/contract style as the wave-1
transitions parity table. When the write lands on SurrealDB, the RELATE edge is
authoritative and no parity row is written.

### Graph-based resume

- New `DatabaseClient.latest_activity_per_issue(limit=10)`: for each
  non-terminal issue that has `worked_on` edges, the most recent linked session
  or loop run with its status and timestamp. SurrealDB: one graph query over
  `issues` projecting `<-worked_on<-sessions` and `<-worked_on<-loop_runs`;
  SQLite: a join over the parity table.
- `get_latest_activity` keeps its exact return shape and gains a new `issues`
  key — the linked issue numbers — only when edges exist for the winning row.
- `digest.py` builds the resume command from `latest_activity_per_issue` when
  it returns rows. The `#(\d+)` regex over the task string remains only as the
  fallback branch for legacy sessions with no edges, marked deprecated with a
  reference to this ADR. Expand/contract: the fallback is deleted next release,
  once every live session row predating the edge has aged out of resume
  relevance.

### Produced edge wired into the workflows

`link_session_handoff` (the `produced` edge, shipped in ADR-0011) existed as a
write API no workflow called. The command files (solomon-start, solomon-review,
solomon-release, solomon-bug, solomon-issue) now instruct the agent to pass
`issues=[...]` to `save_session` and to link the saved session to the handoff
it logged, so the episode graph (session -> produced -> handoff, session ->
worked_on -> issue) is written where the commands already write memory.

### Consequences

- Positive: resume becomes a typed graph query; the digest stops parsing prose;
  per-issue activity history is one traversal; the produced edge finally gets
  written.
- Negative: one release carries both the graph path and the deprecated regex
  fallback; the SQLite store gains one more parity table.
- Follow-ups: delete the digest regex fallback next release; consider a
  `worked_on` edge from handoffs if reviews start running without sessions.

## More information

Review finding F3 (2026-07-04). Builds on ADR-0011 (graph model) and ADR-0016
(closed durability funnel; edges mirrored and replayed as RELATE). Recorded in
the project memory via `save_decision`.
