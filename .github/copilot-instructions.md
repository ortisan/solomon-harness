# solomon-harness — Copilot Instructions

This project's rules and agent definitions are maintained in one place:
`agents/AGENTS.md`. Read it, plus the relevant `agents/<name>/`, before
generating any code or text.

Core rules (full detail in `agents/AGENTS.md`):

- Strict Test-Driven Development is mandatory; follow SOLID and keep the design modular.
- No emojis, icons, or AI cliches ("delve", "leverage", "dive into", "in summary")
  in any output, including commit messages and comments. Write in a direct,
  professional, senior-engineer tone.
- Plan in `PLAN.md` before non-trivial changes; mock external services in tests.
- **Specs:** `docs/specs/` (specification documents defining requirements and design constraints for feature issues).
- **ADRs:** `docs/adrs/` (Architectural Decision Records tracking architecture and technology selections).

Each specialist agent is defined under `agents/<name>/` (persona, the role in
`agents/<name>.md`, and skills). The shared memory client lives in
`solomon_harness/tools/database_client.py`.
