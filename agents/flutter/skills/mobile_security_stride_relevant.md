## Mobile security (STRIDE-relevant)


Flutter ships installable binaries, so threat-model the client: **Spoofing** (enforce auth tokens, certificate pinning), **Tampering** (build with `--obfuscate --split-debug-info`, validate all platform-channel input), **Repudiation** (audit-log sensitive actions server-side), **Information disclosure** (store secrets in `flutter_secure_storage`/Keychain/Keystore, never in source, prefs, or logs; redact PII from crash reports), **Denial of service** (timeouts and backoff on network calls), **Elevation of privilege** (least-privilege platform permissions, never trust client-side gating alone). No API keys or credentials committed to the repo.
