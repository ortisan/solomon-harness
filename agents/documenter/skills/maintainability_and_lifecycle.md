## Maintainability and lifecycle


- Assign an owner to every page. Unowned docs rot.
- Review cadence: re-validate each page at least every 90 days; flag any page past 180 days since `last_reviewed` as stale and block it from the "current" navigation.
- Tie docs to the workflow lifecycle: documentation is part of Release and Documentation, synced with `scripts/wiki-sync.sh`; a release is not done until its docs and changelog are updated.
- Treat a doc bug like a code bug: file an issue, fix at the source, verify the link/example, and close. Do not patch symptoms in a downstream copy.
- Persist documentation decisions and structure changes to project memory (decisions, handoffs) so the next agent inherits the rationale.
