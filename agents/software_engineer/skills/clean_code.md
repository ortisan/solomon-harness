## Clean code


- Functions do one thing at one level of abstraction. Keep them short; if a function needs section comments, split it.
- Cap nesting at two levels. Use guard clauses and early returns instead of `else` pyramids.
- Keep cyclomatic complexity at or below 10 per function. Check with `ruff` (C901) or `radon cc`. Split anything higher.
- Names carry intent. No single-letter names outside short comprehensions or math. No abbreviations that need a glossary. Booleans read as predicates (`is_active`, `has_pending`).
- No magic numbers or strings. Promote them to named constants or enums.
- Type-annotate every public function signature (PEP 484). Run `mypy --strict`. Do not let `Any` leak across module boundaries.
- Self-documenting code first; comments explain why, not what. Delete dead code and commented-out blocks rather than shipping them.
- Apply the rule of three before abstracting. Duplicating twice is fine; extract on the third occurrence so you abstract the real pattern, not a guess.
- Prefer pure functions and immutable data. Push side effects (IO, network, clock) to the edges so the core stays testable.
