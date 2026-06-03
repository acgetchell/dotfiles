---
name: rust-cargo-hygiene
description: "Audit Cargo.toml, feature flags, MSRV, lints, and crate-level configuration for release readiness on changed manifests or whole-repo baseline audits when explicitly requested. USE FOR: Cargo.toml review, feature flag design, default-features gating, dev/build/runtime dependency placement, dependency version specifiers, MSRV pin, edition, [lints] table, clippy.toml/rustfmt.toml, crate-level deny/warn lints (including unsafe_code = forbid), workspace inheritance, [package.metadata.docs.rs] config, semver-sensitive Cargo manifest changes, preparing a crate release. DO NOT USE FOR: source-level Rust review (use rust-production-review or other Rust skills), CI/CD workflow logic, non-Rust packaging, or unrelated unchanged manifests unless a baseline audit is requested."
---

# rust-cargo-hygiene

Audit `Cargo.toml`, feature flags, MSRV, lint configuration, and other crate-level settings for clarity, semver discipline, and release readiness.

Manifest mistakes break downstream builds quietly: an unintended `default-features = true`, a missing dev-only dependency move, or a slipping MSRV often only surfaces on a user's machine. Treat the manifest as part of the public API.

## Scope

Focus on newly added or modified files such as:

- `Cargo.toml` (root, workspace, and per-crate)
- `Cargo.lock` only when the lock file is committed (binary crates or workspace policy)
- `clippy.toml`, `rustfmt.toml`, `.cargo/config.toml`
- crate-root attributes (`#![deny(...)]`, `#![warn(...)]`, `#![forbid(...)]`)
- `rust-toolchain.toml`

### Scope Modes

Default mode:
- Audit newly added or modified manifests, toolchain files, lint configuration, and crate-root attributes.
- Ignore unrelated unchanged configuration unless it affects the changed manifest surface.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit all workspace manifests, committed lockfile policy, toolchain files, Cargo config, lint configuration, docs.rs metadata, and crate-root lint attributes.
- Prioritize findings by release risk, semver impact, MSRV drift, feature breakage, unsafe/lint policy enforcement, and dependency correctness.
- Do not require fixing every historical hygiene issue in one pass; separate release blockers from cleanup follow-ups.

## Review goals

### 1. Package metadata

Check:

- `name`, `version`, `edition`, `rust-version`, `description`, `license`, `repository`, `documentation`, `homepage`, `categories`, `keywords`, and `readme` are populated where appropriate for a published crate
- `version` follows semver and matches the changelog entry being prepared, when the task is explicitly release-preparation work
- `edition` is set explicitly and matches the rest of the workspace
- `rust-version` is present for any published crate that wants a meaningful MSRV
- `license` field agrees with `LICENSE`/`LICENSE-*` files in the repository

Version-change policy:

- Do not automatically bump `Cargo.toml` package versions, lockfile package versions, README dependency snippets, or related version references during ordinary cargo-hygiene, feature, fix, or review work.
- Treat version bumps as maintainer-driven release work. Only recommend or perform them when the user explicitly asks for release/version-bump work or is following the repository's release procedure.
- If changed code appears semver-sensitive, report the semver implication as a finding or release note. Leave the actual version update to the maintainer unless explicitly instructed otherwise.

Flag:

- missing or stale metadata for a crate about to publish
- mismatched `version` between manifest and `CHANGELOG.md`
- license fields that disagree with the repository's license files

### 2. Dependencies

Check:

- runtime, build, and dev dependencies live in the right tables
- version specifiers are realistic: avoid `*`, avoid pinning to exact patch versions for libraries
- `default-features = false` is set for dependencies that pull in unwanted features by default
- features requested per dependency match what the code actually uses
- optional dependencies are gated through the crate's own feature flags
- workspace inheritance (`workspace = true`) is used consistently to avoid drift between workspace members
- `path` and `git` dependencies are intentional for a published crate (usually replaced by version requirements before release)

Flag:

- runtime use of items only enabled via dev/test
- accidental `default-features = true` on heavy ecosystem crates (e.g., `tokio`, `reqwest`, `serde`)
- duplicated dependencies between root and workspace members at different versions
- transitive features enabled implicitly that change behavior
- direct dependencies on yanked or deprecated versions

### 3. Feature flag design

Check:

- features are additive: enabling a feature should not remove or replace functionality
- default features make sense for the broadest reasonable consumer
- internal "implementation detail" features are documented or prefixed (for example `_internal-*`) so they are clearly unstable
- features that flip safety, dependencies, or runtime behavior are clearly named
- removing or renaming a public feature is treated as a breaking change

Flag:

- non-additive features
- features that silently change MSRV
- public feature names that leak third-party crate names callers should not depend on
- feature combinations that fail to compile

### 4. MSRV and toolchain

Check:

- `rust-version` is consistent with the highest stable feature actually used
- CI tests against the declared MSRV
- `rust-toolchain.toml` is intentional and matches contributor expectations
- bumping MSRV is treated as at least a minor version change for libraries

Flag:

- nightly-only features used in a crate that claims a stable MSRV
- silent MSRV drift through new dependency versions

### 5. Lints and style configuration

Check:

- the `[lints]` table or crate-root attributes set a coherent baseline
- `#![forbid(unsafe_code)]` (or `[lints.rust] unsafe_code = "forbid"`) is set when the project's policy forbids unsafe; this is the right place for that policy, not a code review checklist
- `clippy.toml` rules are documented when non-default
- `rustfmt.toml` matches the project's formatting expectations
- `#![deny(missing_docs)]`, `#![deny(rustdoc::broken_intra_doc_links)]`, and similar are configured for published crates
- lint levels are consistent across workspace members through the workspace `[lints]` table

Flag:

- unsafe-policy crates that lack `forbid(unsafe_code)` enforcement
- per-file `#[allow(...)]` for lints that should be allowed crate-wide (or vice versa)
- workspace members that override workspace lint settings without justification

### 6. Workspace and publishing

Check:

- `[workspace]` inheritance covers shared metadata, dependencies, and lints
- `publish = false` is set for internal-only crates
- `exclude`/`include` are set when the published tarball needs trimming
- `[package.metadata.docs.rs]` is configured when feature flags affect docs.rs builds
- workspace members that should not be published explicitly opt out

### 7. Release readiness

Before a release, also check:

- `CHANGELOG.md` has an entry that matches the manifest version
- documentation has been updated to match the new version before publishing; crates.io does not allow republishing documentation without a version bump
- version references are consistent only within an explicit release workflow; do not introduce the version bump yourself unless the user requested that release step
- `cargo publish --dry-run` would succeed with the current manifest
- yanked or deprecated dependencies are not present
- MSRV declared in `Cargo.toml` matches the value tested in CI

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Manifest, feature, MSRV, lint, or workspace issues with locations

### Required Fixes
- Metadata corrections
- Dependency reorganization or feature changes
- MSRV/toolchain alignment
- Lint configuration changes (including `forbid(unsafe_code)` when policy requires it)
- Workspace or publish setting changes

### Optional Improvements
- Future-friendly metadata, doc, or feature suggestions
