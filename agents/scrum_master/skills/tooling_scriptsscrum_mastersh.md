## Tooling: scripts/scrum-master.sh


This is the single entry point for issues and milestones. The repo has no Git remote, so the script falls back to mock mode; treat mock output as a dry contract and switch with `-R owner/repo` once a remote exists. Use `--dry-run` to preview any call.

```
scripts/scrum-master.sh milestone-create "<title>" "<description>" "<YYYY-MM-DD>"
scripts/scrum-master.sh issue-create "<title>" "<feature|bug|quant|future>" "[description]"
scripts/scrum-master.sh backlog-list
scripts/scrum-master.sh milestone-list
```

Issue type maps to the template under `.github/ISSUE_TEMPLATE/`: `feature` to `feature_conception.md`, `bug` to `bug_report.md`, `quant` to `quant_model_hypothesis.md`, `future` to `future_ideas.md`. Pick the type that matches the work; a trading model goes in as `quant`, not `feature`, so the hypothesis fields are captured.

Persist the same records in project memory so other agents see context. Init once with `python agents/scrum_master/main.py db-init`, then use the `solomon-memory` MCP tools. The ones you rely on most: `create_milestone`, `log_issue`, `get_open_issues`, `get_issue`, `log_handoff`, `save_session`, `save_decision`, `get_latest_activity`. Retrieval and adjacent tools also exist when you need them: `get_decision`, `get_session`, `save_memory`, `get_memory`, and `save_backtest` for quant results. Log a handoff every time you route work to another specialist and record planning trade-offs with `save_decision`.
