# ADR-0024: Deterministic Local Codebase Scanning for Living Project Memory

- Status: accepted
- Date: 2026-07-05
- Deciders: software_architect, software_engineer
- Issue: #7

## Context and problem statement

To implement a living project memory, the harness needs to extract structural, dependency, stack, and architectural pattern information from the local codebase. We must decide whether to perform this extraction purely deterministically using local Python parsing (AST/regex/file walking) or to delegate the semantic pattern extraction to a host LLM during execution.

## Decision drivers

- **Performance**: The loop start and handoff hooks must execute quickly (adding < 2s to the execution time).
- **Hermeticity and Cost**: The harness must be self-contained and not depend on external APIs or cause additional LLM token costs.
- **Safety**: The harness must not run LLM calls itself, keeping all semantic orchestration to the host tool.

## Considered options

1. **Host-LLM-assisted extraction**: Delegate structure and pattern extraction to the host LLM at runtime via MCP calls.
2. **Deterministic local codebase scanning**: Walk the codebase, parse local package imports, read configuration files (such as `pyproject.toml`), and list files under known paths (such as `docs/adr/` and `agents/`) using Python.

## Decision outcome

Chosen option: **Deterministic local codebase scanning** (Option 2).

### Justification
Option 2 meets all performance, cost, and design boundaries. By analyzing local imports and scanning configuration files, we extract all required modules, dependencies, stack, entry points, and recurring architectural patterns (ADRs, agents, commands) in a fast, hermetic, and deterministic manner. This completely avoids the latency, cost, and reliability risks of calling LLMs from within the harness, which aligns with the global policy of keeping the harness LLM-free.

### Consequences

- **Positive**:
  - Scanning is extremely fast (takes milliseconds when cached via manifest comparisons).
  - Absolutely zero token cost and zero dependency on network availability.
  - Predictable, deterministic behavior that is easy to unit test.
- **Negative**:
  - The extraction of "architectural patterns" is structural (e.g. counting ADR files and listing registered agents/commands) rather than deep semantic analysis.
- **Follow-ups**:
  - If deep semantic enrichment of the project model is needed, the host tool can query the local model (via the memory MCP) and enrich it.

## More information

This decision is also recorded in the project memory via `save_decision`.
