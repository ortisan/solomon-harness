## Dependency and supply-chain security


- Pin every dependency to an exact version and verify integrity with hashes (`pip install --require-hashes`, or a locked `uv.lock`/`requirements.txt` with hashes). Unpinned ranges are a supply-chain hole.
- Scan continuously: `pip-audit` (no account required, queries the PyPA advisory DB and OSV) as the baseline, optionally `safety` (current versions need a registered account for the full DB); add `trivy fs` or `grype` as a second source and for container images if any.
- Generate and publish an SBOM in CycloneDX or SPDX format per release so consumers can audit what shipped.
- Automate update PRs with Dependabot or Renovate, but never auto-merge without the full scan and test suite passing.
- License compliance: block copyleft licenses (GPL/AGPL) that conflict with the project license, and any unknown/unlicensed package. Keep an allowlist.
- Guard against typosquatting and dependency confusion: review new transitive packages, prefer a known index, and verify package names against the intended source.
