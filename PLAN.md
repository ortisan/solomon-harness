# Plan

Expose the project memory as an MCP server so the host tools (Claude Code,
Codex, Copilot) can read and write decisions, memory, issues, sessions and
handoffs directly. The agent loop lives in those tools; this gives them the
memory the harness already implements.

## Scope

- In:
  - solomon_harness/memory_service.py: a JSON-serializable wrapper over
    DatabaseClient (the testable core), reusing a single client per service
  - solomon_harness/mcp_server.py: a thin MCP server (FastMCP) that registers the
    MemoryService methods as tools; the mcp SDK is imported lazily so the module
    imports without it
  - .mcp.json: project-scoped Claude Code registration of the server
  - pyproject.toml: declare mcp; regenerate the lock
  - agents/AGENTS.md: update the memory section to document the server and tools
  - tests/test_memory_service.py: round-trip tests against a temp DB (no mcp)
- Out:
  - SurrealDB statement correctness, auth/permissions on the server, writing
    global Codex/Copilot configs (documented instead)

## Design

- MemoryService(harness_dir=None, db_path=None) holds one DatabaseClient and
  exposes save_decision/get_decision, save_memory/get_memory, log_issue/
  get_open_issues/get_issue, create_milestone, save_backtest, save_session/
  get_session, log_handoff, get_latest_activity. Each returns a plain dict.
- resolve_harness_dir walks up to the solomon_harness package so the server uses
  the project-root memory store regardless of cwd.
- mcp_server.build_server() imports FastMCP lazily and registers each tool;
  `python -m solomon_harness.mcp_server` runs it over stdio.
- The mcp dependency is declared but need not be installed for the tests, which
  exercise MemoryService directly.

## Action Items

- [ ] Red: tests for the decision/memory/issue/session/handoff round-trips and
      get_latest_activity against a temp DB, plus resolve_harness_dir.
- [ ] Green: implement memory_service.py.
- [ ] Add mcp_server.py (FastMCP wiring, lazy import).
- [ ] Create .mcp.json and declare mcp in pyproject; regenerate the lock.
- [ ] Update the memory section of agents/AGENTS.md.

## Verification

- python3 -m unittest discover -s tests passes (no mcp required).
- python3 -c "import solomon_harness.mcp_server" imports cleanly without mcp installed.
- ruff check passes; the 14 agent eval suites still pass.

## Open Questions

None
