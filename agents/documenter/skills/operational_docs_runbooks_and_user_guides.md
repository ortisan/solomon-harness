## Operational docs: runbooks and user guides


- Runbooks are written for an on-call engineer at 3 a.m.: alert/symptom, business impact and severity, diagnosis steps, remediation commands, rollback procedure, and escalation contacts. Every step is copy-pasteable and tested in a drill.
- User guides are task-organized, not feature-organized. Lead with what the user wants to accomplish. Include prerequisites, a verification step, and a troubleshooting section for the top failures.
- Changelogs follow Keep a Changelog and Semantic Versioning. Group entries under Added, Changed, Deprecated, Removed, Fixed, Security. Write entries for users, not commit-by-commit.
