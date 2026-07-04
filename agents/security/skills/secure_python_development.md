# Secure Python Development

Concrete wrong-versus-right patterns for the vulnerability classes that actually appear in Python codebases: injection, unsafe deserialization, subprocess misuse, path traversal, SSRF, timing side-channels, archive extraction, and unsafe parsing. The stance: validate at the boundary with an allowlist, keep user data out of every interpreter (SQL, shell, YAML, pickle), and prefer the standard library's safe construction over sanitizing your way out.

## Injection: parameterized queries only

Never assemble a query with user input by f-string, `%`, `+`, or `.format()`. This applies to SQL and equally to SurrealQL in the memory client.

```python
# WRONG - classic injection
cur.execute(f"SELECT * FROM issue WHERE status = '{status}'")

# RIGHT - bound parameter (sqlite3)
cur.execute("SELECT * FROM issue WHERE status = ?", (status,))

# RIGHT - SurrealQL bound variable
await db.query("SELECT * FROM issue WHERE status = $status", {"status": status})
```

Identifiers (table or column names) cannot be bound; map them through a hardcoded allowlist dict instead of interpolating the raw value. Validate input shape and semantics (type, length, range, encoding) with pydantic or jsonschema before it reaches any sink; reject by default.

## Deserialization: pickle is code execution

`pickle.loads` on attacker-influenced bytes is arbitrary code execution by design — `__reduce__` runs on load. The same applies to `shelve`, `marshal`, and joblib/torch model files from untrusted sources.

```python
# WRONG - executes attacker code on load
obj = pickle.loads(blob)

# RIGHT - data interchange uses a data format
obj = json.loads(blob)
```

If a binary format is unavoidable between trusted components, authenticate it first: `hmac.compare_digest` over a keyed MAC of the bytes, verify, then deserialize. For YAML, `yaml.safe_load` always — full `yaml.load` with the default loader instantiated arbitrary objects (CVE-2017-18342, fixed as a default only in PyYAML 5.1+, and `yaml.unsafe_load` remains). This repo's `scripts/validate-workflows.py` uses `yaml.safe_load` deliberately; keep that invariant. For XML use `defusedxml` to close XXE and billion-laughs.

## Subprocess: argument lists, never shell=True with input

```python
# WRONG - shell metacharacters in `branch` execute (S602/B602)
subprocess.run(f"git checkout {branch}", shell=True)

# RIGHT - argv list, no shell, timeout, no exception swallowing
subprocess.run(["git", "checkout", "--", branch], shell=False,
               timeout=30, check=True)
```

The `--` separator stops option injection (`branch = "-f"` style). `shlex.quote` exists for the rare case a shell is genuinely required (pipelines over ssh); treat that as a design smell needing review. Never pass secrets in argv — visible in `ps` to all local users.

## Path traversal: resolve, then contain

```python
# WRONG - name = "../../../etc/passwd" escapes the root
path = os.path.join(UPLOAD_ROOT, name)

# RIGHT - canonicalize and prove containment (Python 3.9+)
root = Path(UPLOAD_ROOT).resolve()
path = (root / name).resolve()
if not path.is_relative_to(root):
    raise ValueError("path escapes upload root")
```

`resolve()` collapses `..` and symlinks before the check; comparing unresolved strings is bypassable. Also reject NUL bytes and normalize Unicode before the check.

## SSRF: allowlist the destination

Fetching a caller-supplied URL lets the caller aim your credentials at internal targets — cloud metadata (`169.254.169.254`), localhost admin ports, the SurrealDB RPC socket.

```python
# WRONG
resp = requests.get(user_url)

# RIGHT - scheme + exact-host allowlist, no redirects, timeout
u = urllib.parse.urlsplit(user_url)
if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
    raise ValueError("destination not allowed")
resp = requests.get(user_url, timeout=10, allow_redirects=False)
```

Exact-host matching, not substring (`"example.com" in host` passes `evil-example.com`); this is the same exact-host rule the wiki-bootstrap allowlist shipped with. Redirects re-open the hole, so disable and re-validate each hop if you must follow them. DNS rebinding defeats resolve-then-check patterns; for high-assurance cases pin the resolved IP for the actual connection.

## Timing-safe comparison

`==` on secrets short-circuits at the first differing byte and leaks position through response timing.

```python
# WRONG
if token == expected: ...

# RIGHT
if hmac.compare_digest(token, expected): ...
```

Use it for tokens, MACs, and webhook signatures. Passwords are different: verify via argon2id (`argon2-cffi`) or bcrypt, never by comparing hashes yourself. Generate tokens with `secrets.token_urlsafe(32)`, never the `random` module.

## Archive extraction

`tarfile.extractall()` on an untrusted archive writes outside the target via `../` members or symlinks (CVE-2007-4559, unfixed-by-default for 15 years). PEP 706 filters shipped in 3.12 and were backported to 3.11.4/3.10.12/3.9.17; Python 3.14 finally defaults to `"data"`.

```python
# WRONG on Python < 3.14 - no filter, traversal possible
tf.extractall(dest)

# RIGHT - explicit data filter (this repo's floor is 3.11, which has it)
tf.extractall(dest, filter="data")
```

For `zipfile`, validate each `ZipInfo.filename` against the containment check above and cap total decompressed size to stop zip bombs.

## Remaining defaults

TLS verification stays on (`requests` `verify=True`; never ship `verify=False` even in tests — mock the transport). Frameworks run `debug=False` in production. Error responses to external callers carry a generic message; stack traces, hostnames, and schema details stay in internal logs. `eval`/`exec` on any external string are banned outright.

## Common pitfalls

- Sanitizing input for one sink (HTML-escaping) and passing it to another (shell, SQL) where the escaping is meaningless — encode per sink, at the sink.
- Building the "safe" query with an f-string because "the value is an int here"; the pattern gets copied to a string field next month. Parameterize unconditionally.
- `shell=False` but a single concatenated string argument, which silently becomes the program name lookup instead of arguments.
- Containment checks with `startswith(root)` on unresolved paths — `/data/../etc` and `/database` both defeat it.
- Allowlisting URL hosts by substring or by `netloc` (which includes `user@host` userinfo tricks) instead of parsed exact hostname.
- Catching the pickle problem but loading untrusted `torch.load`/joblib artifacts, which are pickle underneath.
- `hmac.compare_digest` on values of attacker-controlled type; hash both sides first if lengths must stay secret.
- Trusting a client `Content-Length` or filename header for any security decision.

## Definition of done

- [ ] All queries (SQL and SurrealQL) use bound parameters; identifiers go through hardcoded allowlists; a test proves injection attempts fail.
- [ ] No `pickle`/`marshal`/`yaml.load`/`eval`/`exec` on untrusted data; parsers are `yaml.safe_load` and `defusedxml`; ruff `S` rules (S301, S506, S602) are green.
- [ ] Subprocess calls use argv lists with `shell=False`, `timeout`, `check=True`, and `--` before positional user input.
- [ ] File access from external names proves containment via `resolve()` + `is_relative_to`.
- [ ] Outbound fetches of caller-supplied URLs enforce scheme and exact-host allowlists, disable redirects, and set timeouts.
- [ ] Secret comparisons use `hmac.compare_digest`; tokens come from `secrets`; passwords use argon2id or bcrypt.
- [ ] Archive extraction uses `filter="data"` (tar) or per-member validation plus size caps (zip).
- [ ] TLS verification enabled everywhere; external error responses are generic; regression tests cover each vector above and mock all external services.
