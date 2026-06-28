# Solomon Harness

A multi-agent software development harness with a dual-backend memory layer: SurrealDB as the primary store and SQLite as the fallback.

This harness packages all templates, agent rules, and compilers into a unified Python command-line interface (`solomon-harness`). It enables dynamic project structure extraction, safe execution boundaries, and customizable development configurations.

---

## Directory Structure

```
solomon-harness/
├── .agent/                    # Workspace configuration files
├── .claude/                   # Claude Code integration files
├── agents/                    # Source-of-truth specialist agent definitions
├── memory/                    # Memory storage files (SQLite databases & SurrealDB volume data)
├── pyproject.toml             # Python packaging configuration
├── scripts/                   # Thin wrappers delegating to the CLI module
├── solomon_harness/           # Core library package
│   ├── templates/             # Bundled agent harness and pattern templates
│   ├── tools/                 # Database clients and helper tools
│   ├── bootstrap.py           # Workspace initialization logic
│   ├── cli.py                 # Command line interface and dispatcher
│   ├── compiler.py            # Agent harness compilation engine
│   ├── skills.py              # External skill synchronization tools
│   ├── mcp_server.py          # solomon-memory MCP server
│   ├── memory_service.py      # Memory service layer
│   └── evals.py               # Agent evaluation suites
└── tests/                     # Verification test suites
```

---

## Installation & Setup

Ensure Python 3.10+ is installed. It is recommended to manage the project environment using [uv](https://github.com/astral-sh/uv).

1. Install dependencies and set up the virtual environment:
   ```bash
   uv sync
   ```

2. Expose the CLI globally or in development mode:
   ```bash
   uv pip install -e .
   ```

---

## Workspace Initialization & Harness Compilation

### CLI Subcommands

Once installed, the unified `solomon-harness` command provides the following interface:

- **`solomon-harness init`**: Bootstraps the current workspace. It extracts project metadata (Name, Git origin, detected technologies), prompts for software patterns, generates `CLAUDE.md`, `agents/AGENTS.md`, and compiles initial harnesses. Run with `--non-interactive` to use default values:
  ```bash
  solomon-harness init --non-interactive
  ```

- **`solomon-harness compile`**: Scans the `agents/` directory and compiles harnesses for all discovered agents. It pulls rules and injects configured architectural, observability, or security patterns into each agent.

- **`solomon-harness skills`**: Fetches external agent skills from repositories configured in `skill-sources.json`.
  - List sources: `solomon-harness skills sources`
  - List skills in a source: `solomon-harness skills list <source_name>`
  - Add skill to an agent: `solomon-harness skills add <source_name> <skill_name> --agent <agent_name>`

- **`solomon-harness agents`**: Lists or displays details of active agent definitions.
  - List agents: `solomon-harness agents list`
  - Show agent: `solomon-harness agents show <agent_name>`

- **`solomon-harness db-init`**: Initializes the SQLite database client or connects to SurrealDB to initialize memory schemas.

- **`solomon-harness run [task]`**: Launches the interactive execution loop to simulate agent tasks.

- **`solomon-harness eval`**: Runs agent evaluation test suites.

---

## Memory Infrastructure Setup

The project uses SurrealDB as its primary database backend, with SQLite as the fallback store. SurrealDB provides the document, graph, and vector storage the memory layer relies on. (An optional Spectron-style tri-temporal extension is experimental and not a primary feature.)

Use the provided [docker-compose.yml](file:///Users/marcelo/Documents/Projects/solomon-harness/docker-compose.yml) to deploy a local instance of SurrealDB and the Surrealist IDE:

1. Start the memory stack:
   ```bash
   docker compose up -d
   ```

2. Access the database interfaces:
   - **SurrealDB Client API**: `ws://localhost:8000/rpc`
   - **Surrealist IDE Web Dashboard**: `http://localhost:3000` (Configure to connect to `http://localhost:8000` with username `root` and password `root`).

Data is persistent and stored in `memory/surrealdb/`, which is ignored by Git configuration.

---

## Customization & Custom Components

### Adding External Agents
To register a new agent, create a markdown specification under `agents/<name>/agents/<name>.md`. Upon running `solomon-harness compile`, the tool automatically compiles a new agent harness under `agents/<name>/`.

### Overriding Templates
The compilation uses bundled templates inside the package directory. To override templates globally in a workspace:
1. Create a `templates/harness` or `templates/patterns` folder in the project root.
2. The compilation engine will automatically prioritize local templates over the bundled ones.

---

## Verification

Run the test suite using unittest:
```bash
uv run python -m unittest discover -s tests
```
