## Common pitfalls


- Committing to more than measured velocity, then carrying spillover every sprint. Cut scope, not the buffer.
- Letting issues exist without templates, so quant hypotheses ship without Sharpe, drawdown, or leakage checks defined.
- Adding features to a `release/*` branch. Stabilize only.
- Merging a release into `main` but forgetting to merge back into `develop`, which loses the version bump and reintroduces fixed bugs.
- Trying to use a `!` breaking-change subject marker, which the commit-msg hook rejects. Use the `BREAKING CHANGE:` footer.
- Treating standup as a status report to the Scrum Master instead of owner-to-owner coordination, and solving blockers in the meeting.
- Mislabeled commits (`chore` for a feature) that break release-note generation and semantic versioning.
- Closing a milestone with open child issues silently deferred and no reason recorded in memory.
- Skipping the `PLAN.md` artifact and starting Execution, which breaks the lifecycle ordering.
