---
name: mcp-server-engineering
description: Governs designing, implementing, and evolving an MCP (Model Context Protocol) server and the tool surface it exposes to a model, covering tool scoping and naming, JSON-schema input validation, model-actionable error strings, stdio versus HTTP transport, security of tool inputs and outputs, and testing with the MCP Inspector. Use when designing, implementing, or reviewing an MCP server or its tool definitions, as distinct from an HTTP/REST API (rest_api_implementation) or a driven-port adapter (hexagonal_architecture_ports_and_adapters).
---

# MCP Server Engineering

An MCP server is a contract with a model, not a human client: every tool name, schema, and error string is read and acted on by an LLM, so the bar is whether the model can pick the right tool and recover from a wrong call, not whether the interface is RESTful. Adapted from Anthropic's mcp-builder skill (anthropics/skills, Apache-2.0). This repository ships one: `solomon_harness/mcp_server.py`, the `solomon-memory` server, built on the Python `mcp` package's `FastMCP` and registered for Claude Code in `.mcp.json` (`uv run python -m solomon_harness.mcp_server`); it is the resident example below.

## Shape the tool surface for the model, not the API

Prefer a small number of well-scoped tools over one-to-one endpoint wrappers; each tool should do one coherent thing (`save_decision`, `get_open_issues`) so the model composes calls instead of guessing among overlapping options. Name tools `{service}_{action}_{resource}` in snake_case (`slack_send_message`) so they stay unambiguous when several MCP servers share one host session. `solomon_harness/mcp_server.py` registers bare verbs (`save_decision`, `get_memory`, `log_issue`) with no `memory_` prefix; that is safe only while `solomon-memory` is the sole memory-shaped server on the host — a second server exposing `save_decision` collides, and the fix is a prefix, not a docstring. Write each docstring for the model reading it as the tool description: what it does, what it deliberately does not do, and which sibling tool to prefer instead (`get_claim_holder`'s docstring already does this, pointing to `solomon-harness claim status` as the authoritative read).

## Input schemas carry the validation, not the tool body

Every parameter needs a type and a description the model can use to fill it correctly; FastMCP derives the JSON schema from the function signature, so an untyped or `Any` parameter ships a useless schema. Prefer a Pydantic model for multi-field or constrained input (`Field(ge=1, le=100)`, a `Literal` for an enum-like status) over `if` checks in the tool body — the model sees the constraint before it ever calls the tool, which avoids a wasted round trip. `solomon_harness/mcp_server.py` validates by plain typed parameters (`github_id: str`, `milestone_id: Optional[str] = None`), adequate for simple scalars but not for a closed set like "status is open or closed" — a `Literal` field pushes that constraint into the schema. Add tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) so a host can tell `get_open_issues` from `block_issue` without parsing prose; treat them as routing hints, never as the authorization check itself.

## Errors are a message the model has to act on

A tool error is not a forwarded stack trace; it is an instruction. Catch the specific exception, not bare `Exception`, and return what was wrong plus what to try next: `"Error: milestone_id not found. Call list_milestones for valid ids."` beats `"KeyError: '42'"`. Report failures as an `isError` result inside the tool's own response, not a protocol-level JSON-RPC error, so the model reads the message and retries with corrected arguments in the same turn. Leak nothing internal — no paths, SQL, stack traces, or credentials — matching the boundary `robust_defensive_code` and `rest_api_implementation` already draw for HTTP.

## Transport: stdio for a subprocess, HTTP for a shared service

`solomon-memory` runs over stdio (`mcp.run()`'s default): the host spawns it as a subprocess per `.mcp.json`, the right choice for a single-user local integration with no network configuration. A stdio server must never write logging to stdout — that stream is the protocol channel; log to stderr. Move to streamable HTTP (`mcp.run(transport="streamable_http", port=...)`) only when multiple simultaneous clients or a remote deployment is the actual requirement; bind `127.0.0.1` rather than `0.0.0.0` and validate `Origin` against DNS rebinding for a locally-run HTTP server. Avoid the deprecated SSE transport for new work.

## Security is the same boundary, enforced on both sides

Validate every inbound argument as untrusted, including path-like and identifier-like strings (reject `..` segments and paths escaping an expected root). Never place a secret, API key, or credential in a tool's return value or logged arguments — a model transcript is not a vault, and it can be replayed into a PR body or a chat log. Read credentials from the environment at process start (`solomon_harness/mcp_server.py` reads `SOLOMON_HARNESS_DIR` this way) and fail startup loudly when a required one is missing rather than degrading silently.

## Testing an MCP server

Verify the server boots and its schemas resolve before trusting a single tool call: `python -m py_compile` for syntax, then drive the running server with `npx @modelcontextprotocol/inspector` to list tools, inspect generated schemas, and fire sample calls interactively. Unit-test the service object the tools delegate to (`MemoryService` here) so business logic is covered without a live MCP client in the loop — the same fake-over-mock discipline `hexagonal_architecture_ports_and_adapters` requires of any driven adapter. For a shipped server, add a few end-to-end evaluation questions that require several chained tool calls and one verifiable answer, catching a schema or docstring regression that unit tests miss.

## Common pitfalls

- Tool names with no service prefix (`save_decision` instead of `memory_save_decision`), colliding the moment a second server exposes a same-named tool in one host session.
- Returning a raw exception string or traceback as the tool result — the model cannot act on a stack trace, only on a stated cause and remedy.
- A stdio server that `print()`s debug output, corrupting the JSON-RPC stream on stdout; logging must go to stderr.
- Secrets or internal paths embedded in a tool's return payload because it was convenient to return the whole object the service returned.
- One giant `execute_query`-style tool with a free-form string argument instead of several narrow, typed tools — it forces the model to build a mini-DSL instead of calling a schema it already understands.
- Skipping `readOnlyHint`/`destructiveHint` on a mutating tool, so a host cannot tell it apart from a safe read when deciding whether to confirm with the user.
- No test coverage below the MCP layer, so a broken tool is discovered by watching a model fail mid-session instead of by a fast unit test against the service.

## Definition of done

- [ ] Tools are few and well-scoped, prefixed `{service}_{action}_{resource}`, and each docstring states what it does, what it does not do, and which sibling tool to prefer instead.
- [ ] Every parameter has a type and a description; multi-field or constrained input uses a Pydantic model instead of manual checks in the tool body.
- [ ] Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) are set and match actual behavior.
- [ ] Errors are caught by specific exception type and returned as an actionable string naming the cause and the next call to try, with no stack trace, path, or credential leaked.
- [ ] Transport matches the deployment: stdio for a local subprocess (stderr-only logging) or streamable HTTP for a shared remote service, with `127.0.0.1` binding and `Origin` validation when run locally.
- [ ] No secret or credential appears in a tool's return value, logged arguments, or docstring; required credentials are read from the environment and fail startup loudly when missing.
- [ ] The service layer behind the tools is unit-tested independent of a live MCP client, and the server has been driven at least once with the MCP Inspector.
