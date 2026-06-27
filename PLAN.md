# Plan

Workstream 1 from the audit: kill the copy-based duplication. Today the entire templates/harness tree is copytree'd into each agent, so database_client.py (~1090 lines), browser.py, the harness loop and the eval suite exist as 15 byte-identical copies. Extract the shared code into one importable package and reduce each agent to only what genuinely differs.

## Target structure

- solomon_harness/ (single source of truth, importable)
  - __init__.py
  - cli.py (the harness loop: handle_run / handle_eval / handle_db_init / main, parameterized by harness_dir)
  - evals.py (build_agent_suite(harness_dir) -> the shared eval TestSuite)
  - tools/__init__.py, tools/database_client.py, tools/browser.py
- Each agents/<name>/ keeps only its real differences:
  - main.py (thin entrypoint: put repo root on sys.path, call solomon_harness.cli.main(harness_dir=its own dir))
  - .agent/config.json, persona.md, agents/<name>.md, agents/AGENTS.md, skills/
  - no tools/, no tests/ (shared code now lives in the package)
- templates/harness/ becomes the thin template the compiler copies.

## Scope

- In:
  - new solomon_harness/ package (moved database_client.py + browser.py, new cli.py + evals.py)
  - DatabaseClient gains an explicit harness_dir parameter (the client no longer lives inside the agent dir, so it cannot infer the agent from __file__)
  - templates/harness/: thin main.py; remove tools/ and tests/
  - agents/*/: thin main.py; remove tools/ and tests/
  - tests/test_database_client.py: import from the package; rewrite the resolution tests around the explicit harness_dir
- Out:
  - compile-harnesses.py logic (copytree of the now-thin template already yields thin agents; no rewrite needed) and its pattern-injection behavior
  - the real LLM loop, SurrealDB statement correctness, CI install wiring

## Action Items

- [ ] Create the solomon_harness package: __init__ files, move database_client.py and browser.py in.
- [ ] Add the explicit harness_dir parameter to DatabaseClient and resolve config/project-root from it.
- [ ] Write solomon_harness/cli.py (loop parameterized by harness_dir) and solomon_harness/evals.py (suite builder).
- [ ] Replace templates/harness/main.py with a thin entrypoint and delete templates/harness/tools and templates/harness/tests.
- [ ] Thin all 14 agents/*: remove tools/ and tests/, drop in the thin main.py.
- [ ] Repoint tests/test_database_client.py at the package and rewrite the resolution tests to pass harness_dir.

## Verification

- python3 -m unittest discover -s tests passes.
- python3 agents/<name>/main.py eval passes for all 14 agents (each runs the shared suite against its own persona/config).
- python3 scripts/compile-harnesses.py regenerates thin agents in a temp tree under the existing test_compile_harnesses.py without error.
- grep shows database_client.py exists once (in the package), not per agent.
- ruff check passes.

## Open Questions

None
