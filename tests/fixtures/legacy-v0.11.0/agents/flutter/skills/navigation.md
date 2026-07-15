## Navigation


- Use `go_router` for declarative routing, deep links, and web URL support. Define routes centrally; prefer type-safe routes (typed `GoRoute`/codegen) over raw string paths.
- Keep navigation logic out of widgets where possible; trigger it from the application layer's resolved state (e.g. redirect on auth state).
