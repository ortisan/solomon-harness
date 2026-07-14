# ADR-0025: Socratic elicitation gate in issue authoring

- Status: accepted
- Date: 2026-07-14
- Deciders: software_architect, product_owner
- Issue: #222

## Context and problem statement

`/solomon-issue` shapes whatever demand text it receives. A vague demand
("improve the loop") forces the product_owner to guess the problem, persona,
outcome, and scope, and those guesses become the issue — corrected later at
refine or review, the most expensive points. The workflow needed a way to
detect an under-specified demand and elicit the missing facts, without slowing
down demands that are already complete and without ever blocking headless
runs. The doubt-detection criteria had to be explicit, not left to the host
LLM's mood.

## Decision drivers

- Auditability: whether the gate ran, skipped, or was declined must be visible
  on the created issue, and the criteria must be named, fixed, and testable.
- Bounded interaction: the enumerable-decisions rule caps a round at 4
  questions; unbounded questioning would stall well-formed requests.
- Host parity: the same behavior must hold in Claude Code and the Gemini CLI,
  and non-interactive (`dev`) runs must never wait on stdin.
- No new runtime surface: issue shaping is prompt-driven; adding Python
  ambiguity scoring would create a second place where authoring logic lives.

## Considered options

- A prompt-level gate: six readiness criteria in the conventions doc, wired
  into the command as a step, pinned by content-gate tests, with the question
  ladder as a product_owner skill.
- A code-level gate: a Python ambiguity scorer the command calls, returning
  which criteria fail.
- No gate: keep shaping unconditional and rely on refine to catch guessed
  intent.

## Decision outcome

Chosen option "a prompt-level gate", because the interaction happens in the
prompt: the host LLM is the only component that can read a demand, judge the
six criteria, and ask enumerated questions, so putting the checklist anywhere
else adds a runtime surface without adding judgment. The criteria are fixed:
Problem, Persona, Outcome, Boundary, Single reading, Job behind the solution.
The bounds are fixed: at most 3 rounds, at most 4 questions per round, only
for failed criteria. The exits are fixed and verbatim: `Elicitation: skipped —
all 6 readiness criteria met`, `Assumptions (unelicited)` on decline, and
`Elicitation: skipped (non-interactive)` on headless runs. Content-gate tests
in `tests/test_command_gates.py` pin all of it in both hosts' command files,
which is the same enforcement pattern ADR-0020 uses for merge ownership.

### Consequences

- Positive: guessed intent stops entering the backlog silently; every created
  issue records what was asked, skipped, or assumed; a complete demand pays
  zero interaction cost; CI fails if the gate text drifts out of either host's
  command file.
- Negative: the gate's judgment (does a criterion hold?) stays with the host
  LLM, so borderline demands may be judged differently across models; the
  trace line is the audit trail for exactly that reason.
- Follow-ups: extend the gate to `/solomon-bug` and `/solomon-idea` with
  family-specific criteria (out of scope of #222); coordinate the trace line
  with the #221 S1 spec template so specs cite it.

## More information

Issue #222 carries the full acceptance criteria. The convention lives in
`docs/solomon-workflow.md` ("Elicitation gate"), the command wiring in
`.claude/commands/solomon-issue.md` step 2, and the question ladder in
`agents/product_owner/skills/socratic_elicitation.md`. ADR numbers 0023 and
0024 are claimed by main and open PR #212 respectively, which is why this
record is 0025. This decision is also recorded in the project memory via
`save_decision`.
