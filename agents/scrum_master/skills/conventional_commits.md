# Conventional Commits

Governs the commit message format for this repository: Conventional Commits 1.0.0, enforced at write time by the installed `commit-msg` hook, which also bans emojis outright. Treat the spec as the real gate, not a style preference; a malformed subject or any pictograph character aborts the commit.

## The format

Every message follows the 1.0.0 structure: a mandatory subject line, an optional body, and optional footers, each block separated by one blank line.

```
<type>(<scope>): <description>

[body]

[footer(s)]
```

- `type` is mandatory and lowercase. `scope` is optional and lives in parentheses immediately after the type. The colon and a single space precede the description.
- `description` (the subject text) is in the imperative mood: "add walk-forward split", not "added" or "adds". No trailing period.
- The body explains the *what and why*, not the how, in full sentences wrapped at ~72 columns. Use it whenever the change is not self-evident from the subject.
- Footers are `Token: value` trailers (Git trailer syntax): `Refs #142`, `Closes #142`, `Reviewed-by: ...`, and the breaking-change marker described below.

The hook (`scripts/git-hooks/commit-msg`, wired in by `scripts/bootstrap-agent.sh`) validates only the subject line against this exact pattern, so know it precisely:

```
^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|hypothesis)(\([^)]+\))?: .{1,100}$
```

The subject must be 1 to 100 characters after the `: `; keep it under about 72 for readability in `git log --oneline` and GitHub. The scope, if present, must be non-empty inside the parentheses.

## Allowed types

The hook accepts exactly these; using anything else (for example `feature:` or `update:`) fails the commit:

- `feat` — a new capability. Drives a minor version bump and appears in release notes.
- `fix` — a bug fix. Drives a patch bump and appears in release notes.
- `docs` — documentation only.
- `refactor` — a behavior-preserving code change (no feature, no fix).
- `perf` — a change that improves performance.
- `test` — adding or correcting tests.
- `build` — build system or dependency changes (packaging, `pyproject.toml`).
- `ci` — CI configuration and pipeline changes.
- `chore` — maintenance that fits no other type (tooling, housekeeping).
- `style` — formatting and whitespace, no logic change.
- `revert` — reverts a previous commit.
- `hypothesis` — a quant or ML model-hypothesis commit, matching the `quant` issue template. Use it when the commit records a stated hypothesis (target Sharpe, drawdown limit, dataset, architecture).

`feat` and `fix` are the only types that drive release notes, so do not mislabel a feature as a `chore` to dodge attention; that erases it from the changelog. Pick the type by the dominant intent of the change.

## Footers and trailers

Footers carry machine-readable metadata and the issue links. This repository uses three in particular:

- `Refs #<issue>` — references an issue without closing it. Put this in the body/footer of every commit on a branch so the work trail shows on the issue timeline.
- `Closes #<issue>` (or `Fixes #<issue>`) — closes the issue when the change reaches the default branch. Reserve this for the pull request description; in commits it would close the issue the instant the commit merges, often prematurely.
- `BREAKING CHANGE: <explanation>` — the only supported way to flag an incompatible change. The hook validates the subject line, not footers, and it does **not** accept the `!` shorthand (`feat!:`), so never put `!` in the subject. Declare the break in a footer; per SemVer it forces a major version bump regardless of the commit's type.

This repository does not use an attribution or `Co-Authored-By` trailer — its history carries none and the project convention omits it. Do not add one to commit messages.

## Emoji ban and worked examples

The hook scans the entire message (subject, body, and footers) and rejects any character in the emoji and symbol Unicode blocks or whose Unicode category is "Symbol, other" (`So`), or whose name contains EMOJI, SMILEY, or PICTOGRAPH. No icons, no decorative glyphs, anywhere — this is the humanizer rule made executable. The Solomon sage icon is for the live interactive voice only and must never reach a commit message.

A clean feature commit with an issue reference:

```
feat(backtest): add walk-forward split

Replaces the single train/test cut with a rolling walk-forward
window so out-of-sample evaluation tracks regime shifts.

Refs #142
```

A fix with a scope:

```
fix(slippage): clamp negative fill prices to zero

Refs #205
```

A breaking change declared in the footer (note: no `!` in the subject):

```
refactor(api): rename DatabaseClient.save to persist

BREAKING CHANGE: DatabaseClient.save is removed; callers must use
persist, which returns the record id instead of None.

Refs #311
```

## Common pitfalls

- Using an unlisted type such as `feature:`, `update:`, or `wip:`: the subject regex rejects it and the commit aborts. Only the eleven hook types pass.
- Putting `!` in the subject for a breaking change (`feat!:`): the hook does not accept it and will fail; use a `BREAKING CHANGE:` footer instead.
- Any emoji or symbol character anywhere in the message: the hook scans the whole body, not just the subject, and rejects `So`-category glyphs and pictographs. Keep it text-only.
- A subject in the past tense ("added split") or with a trailing period: it violates the imperative-mood convention even though the regex tolerates it; reviewers should still reject it.
- An empty scope `feat(): ...`: the `\([^)]+\)` group requires at least one character inside the parentheses, so this fails; either fill the scope or drop the parentheses.
- `Closes #<issue>` in a mid-branch commit: closes the issue the moment the commit lands, before the feature is done. Use `Refs` in commits, `Closes` only in the PR.
- Mislabeling a `feat` or `fix` as `chore` to keep it quiet: it disappears from the generated release notes and the changelog under-reports the release.
- A subject over 100 characters: the `.{1,100}` bound fails the commit; tighten the subject and move detail into the body.

## Definition of done

- [ ] The `commit-msg` hook is installed (run `scripts/bootstrap-agent.sh` if `git commit` does not validate the message).
- [ ] Subject matches `<type>(<scope>): <description>` with a hook-allowed type, an optional non-empty scope, and 1 to 100 characters of description (kept under ~72).
- [ ] Subject is imperative mood with no trailing period.
- [ ] Body, when present, explains what and why and wraps at ~72 columns, separated from the subject by a blank line.
- [ ] Issue links use `Refs #<issue>` in commits; `Closes`/`Fixes #<issue>` is reserved for the PR description.
- [ ] Breaking changes are declared with a `BREAKING CHANGE:` footer, never with a `!` in the subject.
- [ ] No emojis, icons, or `So`-category symbols appear anywhere in the message.
- [ ] Commit messages carry NO attribution / `Co-Authored-By` trailer (this repository's convention).
- [ ] `feat`/`fix` types are used honestly so release notes stay accurate.
