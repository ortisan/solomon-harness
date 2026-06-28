## Conventional commits


Every commit is validated by the installed `commit-msg` hook (`scripts/git-hooks/commit-msg`, wired in by `scripts/bootstrap-agent.sh`). Make sure it is installed; it is the real gate, not a style suggestion. Format:

```
<type>(<scope>): <description>

[body]

[footer]
```

- Types accepted by the hook: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `hypothesis`. Use `hypothesis` for quant or ML model-hypothesis commits, consistent with the `quant` issue template.
- Subject in imperative mood ("add walk-forward split", not "added"). The hook allows 1 to 100 characters in the subject; keep it under about 72 for readability. No trailing period.
- Scope is optional and lives in parentheses, e.g. `feat(backtest): ...`.
- `feat` and `fix` are the commits that drive release notes; do not mislabel a feature as a chore.
- Breaking changes: the hook does not accept a `!` marker in the subject, so flag the break with a `BREAKING CHANGE:` footer (the hook validates the subject line, not footers).
- No emojis, icons, or decorative elements anywhere in the message. The hook scans the whole message and rejects symbol and pictograph characters.
- The exact subject pattern the hook enforces: `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|hypothesis)(\([^)]+\))?: .{1,100}$`.
- End agent-authored commit bodies with the required trailer, plain and human: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
