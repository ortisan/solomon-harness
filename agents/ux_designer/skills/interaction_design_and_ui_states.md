# Interaction Design and UI States

Design the user flow and the complete set of interface states for every data-driven view, not only the happy-path populated screen, so the product behaves predictably when data is absent, slow, partial, or broken. A design that specifies only the populated state is incomplete and must be rejected; the deliverable is an interaction spec plus a state inventory per screen that the frontend agent implements.

## Model the flow before the screens

Start from the user's primary task, not the navigation tree. Write the task as a goal ("transfer money to a saved payee," "publish a draft post"), then map the primary task path as the shortest ordered sequence of steps that reaches the goal, with each step naming the trigger, the system response, and the decision the user makes next. Branch the path explicitly: every decision point gets its alternative and exception edges drawn, because the exception edges are where the missing states live. Keep the primary path to the fewest steps that still let the user confirm intent before any irreversible action. A flow is ready when a reader can trace goal to completion and every branch terminates in a defined state rather than a dead end.

## The mandatory states for every data-driven view

Any view that renders data, or whose content depends on a network call, must have all of these states designed before it is considered done. The populated state alone is a partial specification.

- Ideal / populated: real content at realistic volume. Design with representative data, including the long name, the 0 value, and the overflowing list, not the tidy three-item mock.
- Empty: three distinct cases, each with a different message and a different call to action, because conflating them strands the user.
  - First-use empty: the user has done nothing yet. Message explains the value of the feature and the CTA starts the task ("Create your first invoice").
  - No-results empty: a filter or search returned nothing. Message names the active query and the CTA clears or broadens the filter ("No results for 'urgent'. Clear filters").
  - User-cleared empty: the user deleted or archived everything that was here. Message confirms the prior content existed and the CTA offers to add or restore ("All tasks complete. Add a task").
- Loading: choose the mechanism by expected duration and whether layout is known.
  - Skeleton screen when the layout is known and the wait is short-to-moderate; it preserves the page shape and reduces perceived wait. Use for initial content loads of lists, cards, and detail panes.
  - Spinner only when the wait is short and the resulting layout is unknown or trivially small (a button's inline busy state, a single value refreshing). A full-page spinner for a known layout is a regression from a skeleton.
  - Optimistic UI when the action almost always succeeds and is cheap to reverse (toggling a like, reordering a list): render the end state immediately, queue the request, and define the rollback state for the rare failure. The rollback state is mandatory, not optional.
- Partial: some data arrived, some failed or is still pending. Specify what renders, what shows an inline placeholder, and what shows an inline error, so one slow widget never blanks the whole screen.
- Error: never a bare state. Every error pairs a specific, plain-language message (what failed and why, in the user's terms) with a recovery path (retry, edit input, contact, or go back). "Something went wrong" with no action is a defect. Distinguish recoverable errors (retry the request) from input errors (fix the field) from terminal errors (the resource is gone, offer navigation away).
- Success: confirm completion with visible feedback proportional to the action. A saved field needs a quiet inline confirmation; a completed multi-step transaction needs an explicit success screen or summary with the next action.

Capture these in a per-screen state inventory table so coverage is auditable:

| Screen | State | Trigger / condition | Message | Primary action |
|---|---|---|---|---|
| Invoice list | Populated | >=1 invoice exists | (n/a) | Open invoice |
| Invoice list | First-use empty | account has never created one | "Create your first invoice to get paid" | New invoice |
| Invoice list | No-results empty | filter yields zero | "No invoices match 'overdue'" | Clear filter |
| Invoice list | Loading | initial fetch in flight | (skeleton rows) | (none) |
| Invoice list | Error | fetch failed | "Could not load invoices. Check your connection." | Retry |

## System feedback and visible status

Every user action gets a system response within the perception window, and the system's current status is always visible (Nielsen's first heuristic). Acknowledge an action immediately even when the result is not ready: disable the submit button and show a busy state on click, then resolve to success or error. Never leave the user guessing whether a tap registered. For background or long operations, show determinate progress when the total is known and indeterminate progress when it is not, and report completion explicitly rather than silently returning to idle.

## Affordances and signifiers (Norman)

An affordance is what an element lets you do; a signifier is the perceivable cue that advertises it. Design the signifier, because users act on what they can perceive, not on the underlying capability. A button must look pressable (raised fill, clear bounds, label), a draggable item must show a grab cue, a disabled control must look disabled and, on attempted use, explain why it is unavailable. Do not hide primary actions behind hover-only reveals on touch devices, where hover does not exist. Match the signifier to the action's weight: destructive actions get a distinct, harder-to-trigger treatment and a confirmation step.

## Microinteractions: trigger, rules, feedback, loops/modes

Specify each small interaction (toggle, like, inline edit, pull-to-refresh) with the four-part structure:

- Trigger: what starts it (user tap, or a system event such as a threshold crossed).
- Rules: what happens and in what order, including the constraints (what is allowed, what is blocked).
- Feedback: what the user perceives at each step, visual, textual, and where relevant motion; tie this to the states above (loading, success, error).
- Loops and modes: how it behaves over time and on repeat (does the meta state change, does a long-press mode exist, what happens on the hundredth use). Define the empty, error, and success feedback for the microinteraction itself, not only its nominal path.

## Form interaction

Pick the input type that constrains errors at the source: native date, number, email, and select controls; a segmented control for two-to-four mutually exclusive choices; a searchable list once choices exceed roughly seven (see Hick's law below). Label every field; never rely on placeholder text as the only label, since it vanishes on input.

Validation timing: validate on blur or on submit, never on every keystroke, because keystroke-level validation flags a field the user has not finished typing and reads as nagging. The exceptions are live affordances that help rather than scold: a password-strength meter and a character counter update live because they guide input rather than reject it. On submit, move focus to the first invalid field and summarize what to fix. Every error message is specific and recoverable: name the field, state the rule, and state the fix ("Card number must be 16 digits" beats "Invalid input"). Preserve the user's entered data across a failed submit; never clear the form on error.

## Design laws and the decision each one changes

- Doherty threshold (system response under 400ms): keep the perceived response to a user action below 400ms to hold attention and flow. This is the trigger for optimistic UI and skeleton screens; when the real response cannot meet 400ms, show acknowledgment within that window and stream or progressively render the rest. Align with Core Web Vitals: target Interaction to Next Paint (INP) under 200ms for the "good" rating, which is the stricter, measurable budget the frontend agent will be held to.
- Fitts's law (acquisition time grows with distance to a target and shrinks with target size): make frequent and primary targets large and place them near where the user's attention or pointer already rests; put the primary action where the eye lands at the end of the flow. Screen edges and corners act as infinitely deep targets for a mouse, so docked toolbars are fast. This sets minimum hit-target sizes and the placement of the dominant action.
- Hick's law (decision time grows with the number and complexity of choices): reduce the count of simultaneous choices on a screen, group and progressively disclose advanced options, and pick one clear default. When a control would expose more than roughly seven peer options, switch from a flat list of buttons to a search or categorized menu. This decides menu structure and how much to reveal at once.
- Jakob's law (users expect your interface to behave like the others they already know): place and behave conventionally (cart at top-right, primary action bottom-right of a dialog, underlined links, left-aligned forms) unless a deviation earns measurably better outcomes. This is the default tie-breaker for layout and pattern choices; novelty must justify the relearning cost it imposes.

## Common pitfalls

- Designing only the populated state: empty, loading, partial, and error are where users actually get stuck, so an unspecified state ships as an accidental blank screen or raw stack trace.
- Collapsing the three empty states into one generic "Nothing here": first-use, no-results, and user-cleared need different messages and CTAs, and a single message misguides at least two of the three.
- Full-page spinner where the layout is known: it discards the perceived-performance gain a skeleton would give and reads as slower even at the same actual latency.
- Optimistic UI without a defined rollback state: the rare failure leaves the UI asserting a success that never happened, corrupting the user's mental model and their data.
- Error states with no recovery path or a vague message: "Something went wrong" gives the user nothing to act on, so they abandon or retry blindly.
- Validating on every keystroke: it flags fields mid-entry and trains users to ignore validation, defeating its purpose. Validate on blur or submit.
- Clearing a form after a failed submit: it punishes the user for the system's rejection and is a common cause of abandonment.
- Hover-only signifiers on touch targets: the affordance is invisible where there is no hover, so the action is undiscoverable on mobile.
- Citing a law without a numeric or structural consequence: "we followed Fitts's law" with no size, placement, or 400ms/200ms budget attached is decoration, not design.

## Definition of done

- [ ] The primary task path is mapped end to end, with every decision point's alternative and exception branches terminating in a defined state.
- [ ] Each data-driven screen has a state inventory covering populated, empty, loading, partial, error, and success.
- [ ] The empty state distinguishes first-use, no-results, and user-cleared, each with its own message and call to action.
- [ ] Loading specifies skeleton vs spinner vs optimistic UI by duration and known-layout, and any optimistic UI defines its rollback state.
- [ ] Every error state pairs a specific, plain-language message with a concrete recovery path.
- [ ] Each microinteraction is specified as trigger, rules, feedback, and loops/modes.
- [ ] Forms validate on blur or submit (not per keystroke), preserve entered data on failure, and give specific recoverable error messages.
- [ ] Each design law cited carries its concrete consequence: a response budget (Doherty < 400ms, INP < 200ms), a target size/placement (Fitts), a choice-count limit (Hick), or a convention followed or justified (Jakob).
- [ ] The output is an interaction spec and per-screen state inventory handed to the frontend agent, not production UI code.
- [ ] The interaction decisions and their rationale are recorded in project memory for the next session.
