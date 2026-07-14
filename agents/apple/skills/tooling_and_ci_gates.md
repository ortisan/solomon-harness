---
name: tooling-and-ci-gates
description: Governs Xcode toolchain pinning, Swift Package Manager lockfile discipline, xcodebuild simulator test runs, SwiftLint/SwiftFormat enforcement, .xcconfig build-setting management, and the branch-specific CI gate matrix for Apple platforms. Use when configuring CI for an Apple project, pinning dependencies, or defining which checks gate a feature, release, or hotfix branch.
---

# Apple Tooling and CI Gates

Pin the toolchain, make every build reproducible from a committed `Package.resolved`, and gate each branch on a defined set of automated checks so that nothing reaches TestFlight or the App Store without passing lint, build, and simulator tests on the exact Xcode the team agreed on. Treat the Xcode version, the resolved dependency graph, and the CI gate list as version-controlled contracts, not local developer preferences.

## Toolchain pinning

A green build on one machine and a red one on another is almost always a toolchain drift, so pin Xcode explicitly. As of mid-2026 the baseline is Xcode 17.x with Swift 6.2; do not let CI float to "latest".

- Commit a `.xcode-version` file (consumed by `xcodes` and read by some CI setups) containing the exact version, for example `17.2`.
- On self-hosted or GitHub-hosted runners, select it before any build:

```bash
sudo xcode-select -s /Applications/Xcode_17.2.app
xcodebuild -version   # assert: Xcode 17.2, Build version 17C...
swift --version       # assert: swift-driver / Swift 6.2
```

- Pin the Swift language mode in the build settings, not just the compiler. `SWIFT_VERSION = 6.0` (the language mode) turns on full data-race safety; staying on `5` silences concurrency diagnostics you want as errors. Migrate deliberately, module by module, using `SWIFT_UPCOMING_FEATURE_*` flags rather than flipping the whole target at once.
- Hosted runner images move; `macos-15` and `macos-26` ship different default Xcodes. Always set the version after `runs-on`, never assume the image default.

## Swift Package Manager: Package.swift and Package.resolved

`Package.swift` declares intent with version ranges; `Package.resolved` is the lockfile that makes a build bit-for-bit reproducible. Commit `Package.resolved` and treat any unexplained change to it as a code-review item.

```swift
// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "Core",
    platforms: [.iOS(.v26), .macOS(.v26)],
    products: [.library(name: "Core", targets: ["Core"])],
    dependencies: [
        // Pin to a compatible range, not a branch. .upToNextMajor is the default for `from:`.
        .package(url: "https://github.com/apple/swift-collections", from: "1.1.0"),
        // Exact pin only when you must freeze a transitive break.
        .package(url: "https://github.com/pointfreeco/swift-snapshot-testing", exact: "1.18.1"),
    ],
    targets: [
        .target(name: "Core", dependencies: [
            .product(name: "Collections", package: "swift-collections"),
        ]),
        .testTarget(name: "CoreTests", dependencies: ["Core"]),
    ]
)
```

Rules:

- Never depend on `branch:` or `revision:` for a shipping dependency. A moving branch defeats the lockfile and makes the build non-reproducible. Use a version range and let `Package.resolved` record the concrete commit.
- `Package.resolved` is JSON with a top-level `"version": 3` (the format Xcode 15+ and SwiftPM 5.9+ write). Do not hand-edit it; regenerate with `xcodebuild -resolvePackageDependencies` or `swift package resolve`.
- In CI, forbid silent re-resolution so a dependency that quietly published a new patch cannot change the build:

```bash
xcodebuild -resolvePackageDependencies \
  -onlyUsePackageVersionsFromResolvedFile \
  -disableAutomaticPackageResolution
```

  If resolution would change the lockfile, the build fails instead of drifting. The equivalent for a pure-SPM package is `swift package resolve --only-use-versions-from-resolved-file`.
- Cache the package cache (`~/Library/Caches/org.swift.swiftpm` and `~/Library/Developer/Xcode/DerivedData/.../SourcePackages`) keyed on the hash of `Package.resolved`. A range-keyed cache serves stale dependencies.

## xcodebuild: build and test on a simulator

Drive CI with `xcodebuild`, not the IDE, and always name an explicit, OS-pinned destination so the test run is deterministic. Pipe through `xcbeautify` (the maintained successor to the abandoned `xcpretty`) for readable logs while preserving the raw log for diagnostics.

```bash
set -o pipefail

# Boot a known simulator; "latest" hides which OS actually ran.
DEST='platform=iOS Simulator,name=iPhone 17,OS=26.0'

xcodebuild test \
  -scheme App \
  -configuration Debug \
  -destination "$DEST" \
  -testPlan UnitTests \
  -resultBundlePath build/UnitTests.xcresult \
  -enableCodeCoverage YES \
  -parallel-testing-enabled YES \
  -onlyUsePackageVersionsFromResolvedFile \
  | tee build/raw-test.log | xcbeautify --report junit
```

- `set -o pipefail` is mandatory: without it a test failure piped into `xcbeautify` returns the formatter's exit code, and CI goes green on a red run. This is the single most common reason a broken test ships.
- Pin the simulator OS in the destination (`OS=26.0`). `OS=latest` silently jumps when the runner image updates, so a passing build can start failing with no code change, or worse, mask a regression on the OS you actually ship.
- Use `.xctestplan` files to separate `UnitTests` (fast, every PR) from `IntegrationTests` and `UITests` (slower, fewer branches). A test plan also pins per-run options: code coverage targets, environment variables, randomized test order, and repetition for flake hunting (`-test-iterations`, `-retry-tests-on-failure`).
- Emit a `.xcresult` bundle and extract coverage with `xcrun xccov view --report --json build/UnitTests.xcresult`. Enforce a floor (for example 70 percent on the core module) and fail the gate below it, but exclude generated and UI-glue code so the number stays meaningful.
- Manage simulators with `xcrun simctl` (`list`, `boot`, `shutdown`, `erase`). Erase between runs on long-lived self-hosted runners to clear stale keychain and `UserDefaults` state that causes phantom failures.

## SwiftLint and SwiftFormat

Run both, with distinct jobs: SwiftLint enforces style and catches smells; SwiftFormat rewrites formatting. They overlap, so disable SwiftLint's purely cosmetic rules and let SwiftFormat own whitespace. Pin both as SwiftPM plugins or Mint-managed binaries so every machine runs the same version (SwiftLint 0.59.x, SwiftFormat 0.57.x as of 2026); a Homebrew install that differs per developer produces noisy, non-reproducible diffs.

```yaml
# .swiftlint.yml
strict: true                 # warnings become failures in CI
opt_in_rules:
  - empty_count
  - first_where
  - force_unwrapping
disabled_rules:
  - trailing_whitespace      # owned by SwiftFormat
analyzer_rules:
  - unused_import
excluded:
  - .build
  - Generated
line_length:
  warning: 120
  error: 160
```

- In CI, run `swiftlint lint --strict` so warnings fail the gate; locally, run it as an Xcode build phase or pre-commit hook for fast feedback, but never let the build phase be the only enforcement (developers can skip it).
- Run SwiftFormat in check mode on CI, write mode locally:

```bash
swiftformat --lint .         # CI: non-zero exit if any file would change
swiftformat .                # local: apply
```

- Keep `--swiftversion 6.2` in `.swiftformat` so the formatter does not rewrite concurrency or macro syntax it misparses under an older assumed version.
- `swiftlint analyze` (the `analyzer_rules`) needs a compiler log, so wire it to a build output path; it catches dead code that lint alone cannot. Run it on a slower cadence (per PR to `develop`, not every push) because it requires a full compile.

## .xcconfig and scheme/configuration management

Move build settings out of the `.pbxproj` and into version-controlled `.xcconfig` files. Settings buried in the project file produce unreadable merge conflicts and let two engineers ship different signing or optimization flags without noticing.

```
// Shared.xcconfig
PRODUCT_BUNDLE_IDENTIFIER = com.example.app
SWIFT_VERSION = 6.0
IPHONEOS_DEPLOYMENT_TARGET = 26.0
SWIFT_STRICT_CONCURRENCY = complete

// Release.xcconfig
#include "Shared.xcconfig"
SWIFT_OPTIMIZATION_LEVEL = -O
SWIFT_COMPILATION_MODE = wholemodule
GCC_OPTIMIZATION_LEVEL = s
ONLY_ACTIVE_ARCH = NO
CODE_SIGN_STYLE = Manual

// Beta.xcconfig — TestFlight build with a distinct bundle id and icon
#include "Release.xcconfig"
PRODUCT_BUNDLE_IDENTIFIER = com.example.app.beta
```

- Map one `.xcconfig` per build configuration (`Debug`, `Beta`, `Release`) and reference secrets and API endpoints through `$(inherited)`-chained values, never hard-coded literals in source.
- Mark CI-run schemes Shared (`Product > Scheme > Manage Schemes > Shared`) so they are checked in under `xcshareddata/xcschemes`. An unshared scheme exists only on one machine and `xcodebuild -scheme` fails on the runner.
- Keep secrets out of `.xcconfig` files that ship in the repo. Inject signing identities and API keys at build time from the CI secret store; an `.xcconfig` is plaintext in Git history.
- Use distinct bundle identifiers for `Beta` and `Release` so a TestFlight build can sit beside the App Store build on a tester's device, and so push and associated-domain entitlements are scoped per environment.

## CI pipeline and branch gates

Define the pipeline as code and make the gate list explicit per branch type, aligned to Git Flow. The principle: the closer a branch is to production, the more gates it must clear.

GitHub Actions, the pull-request gate:

```yaml
name: ci
on: { pull_request: { branches: [develop, main] } }
jobs:
  verify:
    runs-on: macos-26
    steps:
      - uses: actions/checkout@v4
      - run: sudo xcode-select -s /Applications/Xcode_17.2.app
      - uses: actions/cache@v4
        with:
          path: ~/Library/Developer/Xcode/DerivedData/**/SourcePackages
          key: spm-${{ hashFiles('**/Package.resolved') }}   # lockfile-keyed, not range-keyed
      - run: swiftlint lint --strict
      - run: swiftformat --lint .
      - run: |
          set -o pipefail
          xcodebuild test -scheme App -configuration Debug \
            -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.0' \
            -testPlan UnitTests -resultBundlePath build/r.xcresult \
            -onlyUsePackageVersionsFromResolvedFile \
            | xcbeautify --report junit
```

Xcode Cloud equivalent: configure workflows in App Store Connect with start conditions per branch, and customize behavior with the `ci_scripts/` hooks (`ci_post_clone.sh` to install SwiftLint/SwiftFormat via Mint, `ci_pre_xcodebuild.sh` to inject secrets, `ci_post_xcodebuild.sh` to upload artifacts). Xcode Cloud handles signing and TestFlight delivery natively, which removes `fastlane match` from the release path.

Gate matrix:

| Branch type | Required gates |
| --- | --- |
| `feature/*`, `bugfix/*` (PR into `develop`) | SwiftLint `--strict`, SwiftFormat `--lint`, build, `UnitTests` plan on a pinned simulator, coverage floor |
| `develop` (post-merge) | All of the above plus `IntegrationTests` and `swiftlint analyze` |
| `release/*` | Full suite including `UITests`, then a signed `archive` and an automated TestFlight upload to internal testers |
| `main` (tagged release) | Full suite, signed `archive`, export with the production profile, App Store / phased release; tag must be a Conventional-Commit-derived version |
| `hotfix/*` | Same as `release/*`, fast-tracked, then back-merged to `develop` |

Archive and export (release branches) with manual signing driven by an App Store Connect API key, so no human Apple ID password sits in CI:

```bash
xcodebuild archive \
  -scheme App -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/App.xcarchive \
  -authenticationKeyPath "$ASC_KEY_PATH" \
  -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID"

xcodebuild -exportArchive \
  -archivePath build/App.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/export
```

- Store the App Store Connect API key (`.p8`), Key ID, and Issuer ID as CI secrets. The `.p8` is a long-lived credential; scope it to the minimum role (App Manager) and rotate it. Never commit it.
- For Fastlane-based pipelines use `match` (signing assets in an encrypted Git repo or S3), `gym` for archive/export, and `pilot`/`deliver` for upload. Run `match` in `readonly: true` on CI so a runner can never regenerate and invalidate the team's certificates.
- Make builds reproducible across runs: a release archive must embed a deterministic build number (derive it from the commit count or the CI run number) so two archives of the same commit are comparable.

## Common pitfalls

- Missing `set -o pipefail` when piping `xcodebuild` into `xcbeautify`/`xcpretty`: a failing test exits 0 and ships. Reject any CI script that pipes a build without it.
- `-destination` using `OS=latest` or no OS pin: the simulator OS silently changes with the runner image, making green builds non-reproducible and masking ship-OS regressions.
- `Package.resolved` not committed, or CI allowed to re-resolve: dependencies float to new patches and the lockfile is meaningless. Require `-onlyUsePackageVersionsFromResolvedFile`.
- SPM cache keyed on the version range instead of `hashFiles('**/Package.resolved')`: the cache serves stale dependencies after a legitimate bump.
- A dependency pinned to `branch:` or `revision:` for shipping code: the build is no longer reproducible and a force-push to that branch can break or backdoor it.
- Build settings edited in the `.pbxproj` instead of `.xcconfig`: unreviewable diffs and per-engineer drift in signing or optimization flags.
- CI scheme not marked Shared: `xcodebuild -scheme` fails on the runner because the scheme lives only in one developer's `xcuserdata`.
- Secrets (API endpoints, `.p8`, signing identities) checked into `.xcconfig` or the repo: plaintext in Git history. Inject at build time.
- Lint enforced only as an Xcode build phase: developers skip or disable it; CI must run `swiftlint lint --strict` independently.
- `fastlane match` run in read-write mode on CI: a runner regenerates certificates and revokes everyone else's. Pin `readonly: true`.
- Coverage measured over generated and UI-glue code: the percentage looks healthy while core logic is untested.
- Xcode version left floating on hosted runners: the same commit builds differently week to week. Pin with `xcode-select` after `runs-on`.

## Definition of done

- [ ] Xcode version is pinned (`.xcode-version` plus an explicit `xcode-select` in CI) and the Swift language mode is set in build settings, not left at the compiler default.
- [ ] `Package.resolved` is committed, format version 3, and CI resolves with `-onlyUsePackageVersionsFromResolvedFile` and `-disableAutomaticPackageResolution`; no `branch:`/`revision:` dependencies in shipping code.
- [ ] SPM cache is keyed on the hash of `Package.resolved`.
- [ ] `xcodebuild test` runs with `set -o pipefail`, an OS-pinned simulator destination, a named test plan, and emits a `.xcresult` with enforced coverage floor.
- [ ] SwiftLint runs `--strict` and SwiftFormat runs `--lint` as independent CI jobs with pinned versions; overlapping cosmetic rules are disabled on one side.
- [ ] Build settings live in `.xcconfig` files chained with `#include`/`$(inherited)`; CI schemes are marked Shared; per-environment bundle identifiers are distinct.
- [ ] No secrets, signing assets, or `.p8` keys are committed; they are injected from the CI secret store at build time.
- [ ] The branch gate matrix is enforced: PRs run lint/format/build/unit tests; `develop` adds integration tests and `swiftlint analyze`; `release/*` and `main` add the full suite, signed archive, and TestFlight/App Store delivery.
- [ ] Release archives sign with an App Store Connect API key (`fastlane match` read-only where used) and embed a deterministic build number derived from the commit or CI run.
- [ ] The pipeline is defined as code (GitHub Actions workflow or Xcode Cloud workflow plus `ci_scripts/` hooks), reviewed like any other change.
