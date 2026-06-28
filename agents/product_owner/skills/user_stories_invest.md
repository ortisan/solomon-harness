## User stories: INVEST


Write stories as: "As a <persona>, I want <capability> so that <outcome>." The persona must be a real user type, not "the user." The outcome must be the reason, not a restatement of the capability.

Every story passes INVEST before it enters a sprint:
- Independent: deliverable without waiting on a sibling story, or the dependency is named.
- Negotiable: states intent, not implementation. No "use a dropdown" unless the control is the requirement.
- Valuable: a user or business sees value on its own.
- Estimable: engineering can size it. If they cannot, it is missing detail or it is a spike.
- Small: fits in one sprint. If it spans more, split it (by workflow step, by data variation, by happy-path vs edge case, by CRUD operation). Avoid splitting along technical layers (frontend story, backend story) because neither delivers value alone.
- Testable: has acceptance criteria you can pass or fail.

Vertical-slice rule: a story must cut through all layers to deliver observable behavior. "Add a column to the table" is a task, not a story.
