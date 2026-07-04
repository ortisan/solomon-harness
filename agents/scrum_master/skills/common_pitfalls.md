# Scrum Master Common Pitfalls

Cross-cutting process failures the Scrum Master must reject across sprint planning, backlog flow, Git Flow, and conventional commits. Each bullet names the defect and the damage it does to velocity data, release integrity, or the project memory record.

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

## Definition of done

- [ ] Sprint commitment stayed within measured velocity; any spillover was re-planned by cutting scope, not by carrying it forward silently.
- [ ] Every in-flight issue was created from its template via `scripts/scrum-master.sh issue-create`, with quant items carrying Sharpe, drawdown, and leakage fields.
- [ ] Any `release/*` branch received stabilization work only, and the release merge reached every long-lived branch it must return to, so no version bump or bug fix is lost.
- [ ] Breaking changes are flagged with the `BREAKING CHANGE:` footer and every commit type matches the change, so the commit-msg hook, release notes, and semantic versioning stay truthful.
- [ ] Standups surfaced blockers for owner-to-owner follow-up; none were debugged inside the meeting.
- [ ] No milestone was closed with open child issues unless each deferral and its reason is recorded in project memory.
- [ ] `PLAN.md` existed before Execution began for every item, preserving the lifecycle ordering.
