## Project workflow integration


Follow the project lifecycle and use the project tooling:
- Conception: create structured issues and milestones with `scripts/scrum-master.sh`, not ad hoc notes.
- Planning: the PLAN.md for any change references the PRD's in-scope list, target files, edge cases, and the verification criteria you defined.
- Persist decisions in project memory: use `save_decision` for scope and prioritization calls, `log_issue` for gaps and risks, and `create_milestone` for release boundaries, so the next agent sees the context and the rationale.
