## Secrets handling


- Never hardcode credentials, API keys, or database passwords in source or commit them to git history. The harness reads credentials from `.agent/config.json` and env (`SURREAL_URL`, `SURREAL_USER`, `SURREAL_PASS`) — keep it that way.
- Store secrets in environment variables or a dedicated manager (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager). Keep keys isolated from application logic.
- Scan for leaked secrets with `gitleaks`, `trufflehog`, or `detect-secrets` as a pre-commit hook and in CI on every push.
- On a leaked secret: rotate it immediately and treat it as compromised. Removing it from git history is necessary but not sufficient — assume it was captured.
- Rotate keys on a fixed schedule and after any suspected exposure. Keep `.env`, key files, and credential dumps out of version control via `.gitignore`.
