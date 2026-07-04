# Scrum Master Definition of Done

The exit gate for work the Scrum Master tracks: what must hold before an issue, milestone, or release counts as delivered. Ready protects the sprint from ambiguity; this gate protects the increment and the project memory from fiction.

## Common pitfalls

- An issue closed as delivered without a milestone link or an estimate — the burndown never counted it, and the velocity data the next plan depends on is corrupted.
- Execution started with no `PLAN.md`, then one written after the fact — the plan documents the outcome instead of gating the work, so edge cases and verification criteria were never enumerated up front.
- A branch cut from the wrong base to save time — the Git Flow merge path breaks and the change lands outside the planned release.
- A commit mislabeled to satisfy the `commit-msg` hook (a feature filed as `chore`) — the hook goes quiet but release-note generation and semantic versioning are silently wrong.
- The owning specialist's quality gate (TDD, mocked services, STRIDE, quant hypothesis fields) taken on the issue's word instead of on gate evidence, so "done" means "claimed".
- Review sign-off that judged readability and style before verifying compliance with the specification, inverting the required review order.
- A release marked complete with `scripts/wiki-sync.sh` never run or the milestone, decisions, and handoffs never written to memory — the next session resumes against a stale picture.

## Definition of done


- [ ] Work item exists as a templated issue with acceptance criteria and an estimate, linked to a milestone.
- [ ] `PLAN.md` written before Execution: changes, target files, edge cases, verification criteria.
- [ ] Branch follows Git Flow and is cut from the correct base (`develop`, or `main` for hotfix).
- [ ] Every commit passes the `commit-msg` hook: allowed type, subject 1-100 chars (keep under ~72), no emoji, breaks flagged via `BREAKING CHANGE:` footer.
- [ ] Owning specialist's quality gate met (TDD, mocked services, leakage and overflow guards, quant hypothesis fields, STRIDE, as applicable).
- [ ] Code review signed off against the specification first, then quality.
- [ ] Release merged to both `main` (tagged) and `develop`; wiki synced via `scripts/wiki-sync.sh`.
- [ ] Milestone, issues, decisions, and handoffs recorded in project memory; all child issues closed or deferred with a recorded reason.
