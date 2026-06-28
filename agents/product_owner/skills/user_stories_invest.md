# User Stories And INVEST

Write every story as a vertical slice of observable user value that passes INVEST before it enters a sprint, and split anything too big using a named pattern rather than by technical layer. The format is fixed: "As a `<persona>`, I want `<capability>` so that `<outcome>`." The persona must be a real user type, never "the user." The outcome must be the reason the capability matters, not a restatement of the capability.

## INVEST: the gate every story passes

- Independent: deliverable without waiting on a sibling story, or the dependency is named explicitly.
- Negotiable: states intent, not implementation. No "use a dropdown" unless the control itself is the requirement.
- Valuable: a user or the business sees value from the story on its own.
- Estimable: engineering can size it. If they cannot, it is missing detail or it is a spike.
- Small: fits in one sprint. If it spans more, split it. A story that cannot be estimated below the sprint boundary is an epic wearing a story's clothes.
- Testable: has acceptance criteria you can pass or fail.

Vertical-slice rule: a story must cut through all layers (UI, logic, data) to deliver behavior a user can observe. "Add a column to the table" is a task, not a story. Splitting along technical layers ("frontend story," "backend story") is forbidden because neither half delivers value alone and neither can be demoed.

## Splitting patterns

When a story fails Small, split it with one of these patterns. Each child must itself be a vertical slice that passes INVEST.

- By workflow step: a multi-step process becomes one story per step. Ship the steps in sequence; each delivers a usable stage.
- By data variation: one story per input type, format, or data class. Start with the common case, defer the rare formats.
- By happy path vs edge case: the main success path is the first story; each error, empty, or boundary path is a follow-up story.
- By CRUD operation: Create, Read, Update, Delete become separate stories. The first slice is usually Create plus Read, because together they let a user do and see something.

Choose the pattern that produces the smallest slice that is still independently valuable. Do not split below the point where a child has no user-observable outcome.

## Worked split: checkout

The original is an epic, not a story:

> As a registered shopper, I want to check out my cart so that I can buy my items.

This cannot be estimated under a sprint and bundles addressing, payment, and confirmation. Split **by workflow step** into three vertical slices, each shippable and demoable:

> 1. As a shopper, I want to enter and validate a shipping address so that my order ships to the right place.
> 2. As a shopper, I want to review an itemized order summary and confirm it so that I catch mistakes before I pay.
> 3. As a shopper, I want to pay with a saved credit card so that I can complete a purchase quickly.

Each slice cuts through UI, logic, and data, passes INVEST, and could be released behind a feature flag without the others. If story 3 is still too large because the payment integration is broad, split it again **by data variation** (payment method):

> 3a. As a shopper, I want to pay with a saved credit card so that checkout is fast (first slice — covers the majority of orders).
> 3b. As a shopper, I want to pay with PayPal so that I can use my existing balance (follow-up).
> 3c. As a shopper, I want to pay with a gift card so that I can spend store credit (follow-up).

Note what was rejected: a "build the payment service" backend story and a "build the payment form" frontend story. Neither is demoable on its own, so neither is a valid slice — that is a layer split, not a vertical one.

## Worked split: manage saved addresses (CRUD)

> As a shopper, I want to manage my saved addresses so that I do not retype them.

Split **by CRUD operation**, sequencing for earliest value:

> 1. As a shopper, I want to add a saved address so that it is available at checkout (Create).
> 2. As a shopper, I want to see my list of saved addresses so that I can confirm what is stored (Read).
> 3. As a shopper, I want to edit a saved address so that I can fix a typo (Update).
> 4. As a shopper, I want to delete a saved address so that old addresses do not clutter checkout (Delete).

Stories 1 and 2 ship together as the first usable increment; 3 and 4 follow. Each is a vertical slice with its own acceptance criteria.

## Common pitfalls

- A persona of "the user" or "the system": it hides who actually benefits and makes the value untestable. Name the real user type.
- An outcome that restates the capability ("so that I can save my address" on a "save my address" story): the so-that must state the reason, not echo the what.
- Layer splits (frontend story, backend story, database story): neither half is demoable, so neither is a valid story. Reject and re-split vertically.
- A story that cannot be estimated under one sprint with no split proposed: it is an epic. Send it back to be sliced.
- Implementation baked into a Negotiable story ("use a modal," "store it in Redis") when the mechanism is not the requirement: it removes engineering's room to choose.
- A "spike" disguised as a feature story: if the team cannot estimate it because the unknown is technical, make it an explicit, time-boxed spike, not a normal story.
- Child stories from a split that have no independent value (a slice that cannot be demoed alone): the split was a task breakdown, not a story split.

## Definition of done

- [ ] The story follows "As a `<persona>`, I want `<capability>` so that `<outcome>`," with a real persona and an outcome that gives the reason.
- [ ] The story passes all six INVEST checks; any named dependency is explicit.
- [ ] The story is a vertical slice cutting UI, logic, and data, with observable behavior that can be demoed.
- [ ] If the story exceeds a sprint, it is split with a named pattern (workflow step, data variation, happy/edge, or CRUD), and every child is itself a vertical slice passing INVEST.
- [ ] No layer splits remain; no child story lacks independent, demoable value.
- [ ] The story carries acceptance criteria so the Testable check is satisfied.
