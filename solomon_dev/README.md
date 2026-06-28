# solomon-dev

The installer and command-line front-end for the solomon-harness multi-agent
development harness. It lives in the same repository as the harness so the CLI and
the engine it ships always match.

## Install into a project

```bash
npx solomon-dev init
```

Detects the project's stack, drops the harness (agents, the `solomon_harness`
package, scripts, config) into the project, installs the git hooks, compiles the
agent harnesses, generates the host-tool integrations, and indexes the codebase.

## Run the delivery workflows headless

```bash
solomon-dev <stage> [args]
```

Stages: `idea`, `issue`, `bug`, `refine`, `start`, `review`, `release`. Each builds
the prompt from `.claude/commands/solomon-dev-<stage>.md` and runs it through the
chosen engine. Select the engine with `SOLOMON_ENGINE=claude|gemini` (default
`claude`). The same workflows are available as `/solomon-dev-*` slash commands
inside Claude Code and the Gemini CLI.

## Templates

`templates/` is a generated, vendored copy of the harness produced by
`scripts/sync-templates.js` (also run on `npm prepack`). It is not tracked in git;
run `npm run sync-templates` to regenerate it during local development. The `files`
field in `package.json` ensures it is included in the published npm package.
