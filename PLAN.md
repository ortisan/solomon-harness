# Plan

Foundation and hygiene slice from the harness audit. Four contained, test-driven changes that fix a live memory-layer defect, stop secret leakage, make the dependency surface reproducible, and unblock CI on a clean runner. The two root-cause rewrites (package extraction and a real LLM loop) are deliberately out of scope here.

## Scope

- In:
  - templates/harness/tools/database_client.py (config resolution + credential env overrides + SQLite WAL/busy_timeout)
  - agents/*/tools/database_client.py (propagate the identical fix; duplication removal is a later slice)
  - .gitignore (recursive rules for vaults and local DB files)
  - Untrack the 15 committed secure_vault.enc files (git rm --cached, working copies kept)
  - pyproject.toml (PEP 621 manifest declaring surrealdb and dev tooling)
  - tests/test_harness_init.py (derive workspace from __file__; behavioral gitignore assertion)
  - tests/test_database_client.py (new tests for the resolution fix and WAL)
- Out:
  - compile-harnesses.py and its pattern-injection behavior
  - .github/workflows/ci.yml (CI install/validator wiring belongs to the CI roadmap item)
  - SurrealDB statement-form correctness and the real agent loop

## Problem

DatabaseClient walks up to the first .git (repo root) and reads repo-root/.agent/config.json, which has no `database` block. So `provider` resolves to None, the SurrealDB branch is never taken, and every agent silently writes to one shared SQLite file. The intended "SurrealDB primary with SQLite fallback" is never selected. Separately, the .gitignore rules for secure_vault.enc and harness.db are anchored to the repo root, so the 15 nested vault files are tracked and a real key would be committed; there is no dependency manifest; and test_harness_init.py hardcodes an absolute path so the suite errors on any clean checkout.

## Action Items

- [ ] Red: add test_reads_harness_local_config_not_repo_root and test_sqlite_uses_wal to tests/test_database_client.py.
- [ ] Red: fix the hardcoded workspace path in tests/test_harness_init.py and replace the literal gitignore-line assertion with a git check-ignore behavioral test on nested paths.
- [ ] Green: resolve the agent-local .agent/config.json in DatabaseClient (fall back to repo-root config for compatibility); keep the existing project-root walk for the shared SQLite path.
- [ ] Green: honor SURREAL_URL / SURREAL_USER / SURREAL_PASS env overrides so credentials need not live in committed config.
- [ ] Green: enable PRAGMA journal_mode=WAL and a busy_timeout on the SQLite connection for safe concurrent access to the shared store.
- [ ] Rewrite .gitignore with recursive rules (**/.agent/secure_vault.enc, **/memory/long_term/*.db, **/memory/short_term/*.json, *.db-wal, *.db-shm).
- [ ] git rm --cached the 15 tracked secure_vault.enc files; confirm git check-ignore now reports them ignored.
- [ ] Propagate the fixed database_client.py to all 14 agents/*/tools/.
- [ ] Create pyproject.toml declaring surrealdb and a dev extra (ruff, mypy); generate a lock if the environment allows.

## Verification

- python3 -m unittest discover -s tests passes on a clean checkout (no absolute paths).
- New tests prove the agent-local config is read and SurrealDB is selected when configured, and that the SQLite store runs in WAL mode.
- git check-ignore returns 0 for nested vault and DB paths; git ls-files lists no secure_vault.enc.
- ruff check passes on changed Python files.

## Open Questions

None
