## Definition of done


- [ ] Work item exists as a templated issue with acceptance criteria and an estimate, linked to a milestone.
- [ ] `PLAN.md` written before Execution: changes, target files, edge cases, verification criteria.
- [ ] Branch follows Git Flow and is cut from the correct base (`develop`, or `main` for hotfix).
- [ ] Every commit passes the `commit-msg` hook: allowed type, subject 1-100 chars (keep under ~72), no emoji, breaks flagged via `BREAKING CHANGE:` footer.
- [ ] Owning specialist's quality gate met (TDD, mocked services, leakage and overflow guards, quant hypothesis fields, STRIDE, as applicable).
- [ ] Code review signed off against the specification first, then quality.
- [ ] Release merged to both `main` (tagged) and `develop`; wiki synced via `scripts/wiki-sync.sh`.
- [ ] Milestone, issues, decisions, and handoffs recorded in project memory; all child issues closed or deferred with a recorded reason.
