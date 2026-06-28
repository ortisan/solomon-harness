## Secure Python development


- Input validation: never trust input from clients, network, env, files, or the database. Validate against a strict schema (pydantic, jsonschema, or marshmallow) before use. Reject by default; allowlist over denylist.
- Parameterized queries only. Never build SQL/SurrealQL by string concatenation with user input. Use bound parameters or prepared statements.
- Output encoding: contextually encode/escape data written to HTML, shell, SQL, or logs. Strip markup before rendering to web clients.
- No dangerous sinks: avoid `eval`, `exec`, `pickle.loads` on untrusted data, and `subprocess(..., shell=True)`. Use `subprocess` with an argument list and `shell=False`.
- Safe parsers: `yaml.safe_load` (never `yaml.load` with the default loader); `defusedxml` for XML to block XXE and billion-laughs.
- Crypto and randomness: use the `secrets` module for tokens and the `argon2-cffi` (argon2id) or `bcrypt` libraries for password hashing. Never MD5/SHA-1 for security; never the `random` module for anything secret.
- Transport: keep TLS verification on (`verify=True` for `requests`); never disable certificate checks. Enforce TLS 1.2 as the floor, 1.3 where the stack supports it.
- SSRF and path traversal: validate and canonicalize URLs and file paths; restrict outbound destinations; resolve and confine paths under an allowed root.
- Safe defaults: `debug=False` in production frameworks; framework `SECRET_KEY` and all credentials come from the environment, never the code.
- Error handling: strip stack traces, hostnames, and schema details from responses to external callers. Return a generic message externally; keep full detail in internal logs only.
