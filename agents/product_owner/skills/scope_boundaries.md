---
name: scope-boundaries
description: Governs drawing and defending PRD scope boundaries - explicit in-scope and out-of-scope lists with reasons, owned assumptions and dependencies, and the scope-change protocol that logs and prices mid-sprint expansion. Use when writing a PRD's scope section or a stakeholder's request.
---

# Scope Boundaries

Scope control governs what a PRD promises and, just as importantly, what it refuses; the product_owner's job is to draw that line explicitly and defend it so delivery does not slip under silent, unowned expansion. The stance is adversarial toward ambiguity: every requirement is either in scope, out of scope, or a logged change, and nothing is allowed to live in between.

## What the product_owner owns vs. does not own

You own the problem definition and the boundary of the solution. You do not own implementation. Your deliverable is the PRD Contract: the authoritative statement of what is in scope, what is out, and how anyone verifies that the result is correct. If a requirement cannot be tested, it is not a requirement yet; send it back to discovery rather than ship it as prose.

| You own | You do not own |
| --- | --- |
| The problem, the user, the "why" and the "what" | The "how": algorithms, data structures, framework choices |
| The in-scope and out-of-scope lists | The technical design and component internals |
| Acceptance criteria (verifiable pass/fail) | The test code and CI pipeline (you set the bar; QA builds it) |
| Priority and sequencing of deliverables | Estimates and capacity (you negotiate; engineering owns the number) |
| The non-functional bars, sourced from specialists | The non-functional implementation (security, sre, ml_engineer own theirs) |

When a stakeholder asks you to specify an implementation, decline and restate the requirement as an outcome. When an engineer asks you to decide whether something is required, answer; that is squarely yours.

## In-scope and out-of-scope lists

Every PRD carries two explicit lists. The out-of-scope list is the more valuable of the two: most scope disputes come from things nobody wrote down, and an item named as excluded cannot later be claimed as an implied promise.

Rules for the lists:

- Each in-scope item maps to at least one acceptance criterion. An in-scope line with no testable criterion is decoration; delete it or sharpen it.
- Each out-of-scope item states a reason and, where relevant, where it went instead ("deferred to v2", "covered by the existing export feature", "explicitly not building"). A bare exclusion invites someone to reopen it.
- Adjacent obvious-looking work goes on the out-of-scope list on purpose. If a feature touches login, say whether password reset is in or out. Silence reads as "in" to engineering and "out" to the sponsor, and that gap surfaces as a missed deadline.
- Record assumptions and dependencies with named owners. An unowned dependency is a risk, not a fact; assign it or escalate it.

## Worked example: a story with explicit Scope and Out-of-scope

```
Story: Export account statement as PDF
As an account holder, I want to download my monthly statement as a PDF
so that I can submit it for a loan application.

Scope (in):
- Generate a PDF for a single selected month from existing statement data.
- Include opening balance, transactions, closing balance, account holder name.
- Download via the existing authenticated session; rate-limited per existing policy.

Out of scope (and why):
- CSV or XLSX export — deferred to v2; not requested by the loan use case.
- Multi-month / date-range export — out; the JTBD is one statement per application.
- Emailing the PDF — out; covered by the existing notification feature, do not duplicate.
- Branded/custom templates — out; no requirement, would expand design + review cost.

Acceptance criteria:
- Given a logged-in holder with transactions in June, When they request the June
  PDF, Then the PDF contains opening balance, all June transactions, and closing
  balance, and the arithmetic reconciles.
- Given a month with no transactions, When the holder requests that month, Then the
  PDF renders with a "No transactions" line and the correct carried balances.
- Given an unauthenticated request, When the export endpoint is called, Then it
  returns 401 and no statement data is emitted.

Assumptions / dependencies (owner):
- Statement data service exposes per-month transactions (owner: dba).
- p95 generation < 2s for a 12-month account (owner: sre — bar, not implementation).
```

The value is in the "Out of scope" block. Without it, "export statement" quietly grows into CSV, date ranges, email delivery, and branded templates, and the team misses the date building things nobody actually asked for.

## Vertical-slice sizing

Slicing work into issues is a scope decision, not an estimation nuance, and it
sits with the product_owner alongside the in-scope/out-of-scope lists: an
issue's boundary is where a testable, demonstrable slice of value begins and
ends, and that boundary is drawn by whoever draws the scope line, not by
whoever happens to be estimating capacity that week.

Default to fewer, larger issues, each a complete vertical slice: the
implementation, its wiring into the rest of the system, and the tests that
cover it, delivered end to end as one unit a reviewer can judge against one
set of acceptance criteria. A slice that stops at "the function exists" and
defers wiring or tests to a follow-on issue is not a vertical slice — it is a
horizontal layer wearing a story's clothing, and it ships nothing a user or
the system can observe until its undated follow-on lands.

Split an issue only at a real boundary, never to make a number look smaller:

- **Dependency** — a contract (an interface, a schema, a protocol) must exist
  and be agreed before its consumers can be built against it. The
  contract-defining slice is its own issue; everything that consumes it is a
  separate, dependent issue.
- **Parallelization** — two slices touch disjoint parts of the system and can
  genuinely proceed as independent, concurrently running work. If they would
  collide on the same files or the same reviewer's attention regardless of
  who works on them, they are not parallelizable and do not need separating.
- **Domain** — the slices require genuinely different toolchains,
  deliverables, or specialist ownership: a backend contract versus its
  frontend consumer, a migration versus the application code that reads it.
  A domain split is real when the Definition of Ready would otherwise ask one
  issue to carry two different owners' acceptance criteria.

What is never a split reason:

- **File or line count.** An issue that touches twenty files because they
  form one coherent slice is correctly sized; splitting it to make the diff
  smaller breaks a vertical slice into artificial layers that ship no value
  on their own and multiplies the ramp-up cost of re-deriving context across
  issues that were never actually independent.
- **A high complexity or risk rating.** Complexity rates implementation
  risk — the likelihood of rework, the need for coordination, the blast
  radius of getting it wrong — never size. A critical-complexity change
  (cross-cutting, high regression risk) still gets exactly one issue if it is
  one coherent slice; the response to high complexity is more scrutiny at
  refinement and review — a tighter RAID entry, a sharper acceptance-criteria
  pass, an extra reviewer lens — not a smaller issue that hides the same risk
  behind an artificial seam. Splitting a high-risk change across issues does
  not reduce the risk; it relocates the seam to where the risk resurfaces,
  now with two half-finished pieces on the board instead of one coherent,
  reviewable change.

A useful check when a story feels too big to write one Given/When/Then block
for: ask whether the discomfort is actually a missing dependency (something
else must exist first), a genuine parallel opportunity (two people could work
on disjoint pieces right now), or a domain seam (two different specialists
own two different acceptance bars). If none of the three apply, the story is
not oversized — it is substantial, and substantial is not a defect. Ten-plus
issues out of one refinement pass on what was described as a single feature
almost always means slices that belong together were separated for no reason
beyond each one "looking smaller"; merge them back before presenting the
split to the team.

## Scope-change protocol

Scope will change; uncontrolled change is the failure, not change itself. When new scope appears mid-sprint, run it through a fixed protocol rather than absorbing it:

1. Write down what changed, why, and what it displaces. New work is never free; name the in-scope item it pushes out or the date it moves.
2. Log it as a decision in project memory with `save_decision` so the trade is auditable and a future session sees why the boundary moved.
3. Adjust priority openly with the sponsor. The choice is theirs to make, but it must be made in the light, not smuggled into a story.
4. Update the in-scope/out-of-scope lists and the acceptance criteria together. Never expand a story's acceptance criteria silently to swallow new work; that is how a one-sprint story becomes a three-sprint surprise.

Defend the boundary. Saying no to out-of-scope work, or "yes, and here is what it costs", is the job. Vague yes-to-everything PRDs are the most common way delivery slips, and the product_owner is the only role positioned to stop it.

## Common pitfalls

- No out-of-scope list. The single largest source of scope disputes; without it, every adjacent feature is arguable and the sponsor and the team assume opposite answers.
- In-scope items with no acceptance criterion. They cannot be verified, so "done" becomes a matter of opinion and the story never closes cleanly.
- Silent acceptance-criteria growth. Absorbing new work by quietly widening criteria hides the cost, breaks the estimate, and destroys trust in the board.
- Unowned assumptions and dependencies. An assumption with no owner is a latent blocker; when it breaks mid-sprint nobody is accountable for resolving it.
- Specifying the "how". Dictating implementation oversteps the role, demotivates engineers, and makes you accountable for technical outcomes you do not control.
- Treating change as failure. Refusing all change is as damaging as accepting all of it; the protocol exists so change is priced and chosen, not blocked or smuggled.
- Splitting an issue by file count or line count instead of a real boundary. A twenty-file diff that is one coherent slice is correctly sized; the split just breaks the vertical slice into unshippable layers.
- Splitting an issue because its complexity or risk rating is high. Complexity rates risk, not size; a high rating calls for more scrutiny at review, not a smaller issue that hides the same risk behind an artificial seam.

## Definition of done

- [ ] The PRD contains an explicit in-scope list and an explicit out-of-scope list.
- [ ] Each out-of-scope item states a reason and, where applicable, where the work went instead.
- [ ] Every in-scope item maps to at least one verifiable acceptance criterion.
- [ ] Adjacent, plausibly-implied work is named as in or out, not left silent.
- [ ] Assumptions and dependencies are listed with named owners.
- [ ] A scope-change protocol is referenced or applied: changes are logged with `save_decision`, the displaced work is named, and priority is renegotiated openly.
- [ ] No acceptance criterion was widened silently to absorb new scope.
- [ ] The PRD does not specify implementation; it states outcomes the responsible specialist or engineer owns.
- [ ] Every requirement that survived is testable; any that is not was sent back to discovery rather than shipped as prose.
- [ ] Every issue is a complete vertical slice (implementation, wiring, and covering tests); any split cites a dependency, parallelization, or domain boundary, never file/line count or a complexity rating.
