---
name: rust-ecosystem-release-train
description: Plan and coordinate synchronized stable-Rust-boundary releases across acgetchell/la-stack, acgetchell/delaunay, acgetchell/markov-chain-monte-carlo, and acgetchell/causal-triangulations. Use for release ordering, milestone scope, crates.io publication dependencies, Rust/MSRV upgrades, cross-repository blockers, release capstones, or keeping Just recipes, GitHub Actions, pinned tools and actions, Cargo and uv dependencies, and Semgrep policies aligned across this public ecosystem.
---

# Rust Ecosystem Release Train

Coordinate the four public crates as one release train while preserving each
repository's ownership boundaries and specialized workflows.

## Load The Ecosystem Contract

Before planning or changing a release:

1. Read [`references/repositories.md`](references/repositories.md) for crate
   roles, dependency edges, and repository-specific release surfaces.
2. Read [`references/tooling-alignment.md`](references/tooling-alignment.md)
   when assessing release readiness or changing shared tooling, dependencies,
   pins, CI, or Semgrep policy.

Exclude private or unpublished repositories from this public skill. Do not
infer or expose their names, dependencies, issues, or release plans.

## Enforce The Release Contract

- Synchronize ecosystem releases at intentional stable Rust boundaries.
- Treat the selected stable Rust release as a public MSRV boundary. Align each
  repository's manifest, pinned toolchain, Clippy MSRV, active documentation,
  and CI before publishing its release.
- Use crates.io versions for inter-repository dependencies. Never commit Git or
  path dependencies as a substitute for an upstream release.
- Distinguish **code merged** from **crate available downstream**. A downstream
  release remains blocked until the required upstream version is published on
  crates.io and can be resolved normally.
- Permit development and isolated prepublication validation in parallel, but
  publish in dependency order.
- Do not hard-code current versions, milestones, pins, or Rust dates in this
  skill. Discover them from manifests, locks, GitHub, crates.io, and official
  Rust sources on every planning run.

Use this publication graph:

```text
stable Rust ─→ la-stack ─→ delaunay ───────────────┐
          └─→ markov-chain-monte-carlo ────────────┤
                                                    └─→ causal-triangulations
```

`la-stack` and `markov-chain-monte-carlo` may publish in parallel after the
Rust boundary. `delaunay` must consume the published `la-stack` release.
`causal-triangulations` must consume the published `delaunay` and
`markov-chain-monte-carlo` releases.

## Capture Current State

For every repository in the graph, inspect:

- package version, `rust-version`, public dependency requirements, and lockfile;
- `rust-toolchain.toml`, `clippy.toml`, active MSRV documentation, and target matrix;
- latest GitHub and crates.io releases;
- open milestones, release issues, native dependency edges, and open PRs;
- `justfile`, workflow files, Dependabot configuration, and action/tool pins;
- `pyproject.toml`, `.python-version` when present, `uv.lock`, dependency groups,
  overrides, and support-package version;
- `semgrep.yaml`, repository-owned rules, fixtures, fixture validators, and
  Semgrep CI integration.

Prefer repository files and native GitHub metadata over issue-body prose. Use
official Rust release sources for schedules and final release notes.

## Build The Release Plan

1. Create or identify one Rust-adoption issue and one release-capstone issue
   for each participating release.
2. Treat a release milestone as a publication contract. Review every open item;
   keep genuine release gates and move unrelated work rather than silently
   delaying the train.
3. Make each release capstone blocked by all retained local gates and by the
   release capstone of each upstream crate it consumes.
4. Make downstream integration work depend on the upstream **published-release
   capstone**, not merely on the implementation issue that introduced an API.
5. Work bottom-up. After each publication, update downstream Cargo requirements
   and locks through the registry, then run the downstream contract validation.
6. Keep the final ecosystem capstone open until the published crates resolve
   without overrides and the complete downstream validation passes.

Before stable ships, finish compatible feature and defect work, audit beta
compatibility, and prepare release candidates. Do not close the stable-Rust
adoption gate until the final release notes and stable toolchain have been
checked.

## Align Shared Tooling

Treat tooling alignment as semantic synchronization, not textual sameness.
Propagate a shared improvement when the same contract applies; retain a
repository-specific difference when its workload or scientific role requires
it, and record the rationale.

For each release train, compare and intentionally reconcile:

- canonical Just recipe names, composition, and operator-facing behavior;
- GitHub workflow purposes, triggers, permissions, matrices, artifact handling,
  and immutable action pins;
- repository-owned tool pins and Dependabot coverage;
- Cargo dependency versions, feature choices, locks, MSRV, and release profiles;
- Python baseline, support-package metadata, uv dependency groups, exact tool
  pins, security overrides, and locks;
- Semgrep rule coverage, include/exclude surfaces, fixture conventions,
  diagnostics, SARIF upload, and validation commands.

Never bulk-copy configuration without checking the receiving repository's
commands, features, platforms, artifacts, and failure contracts. Validate the
shared contract locally and in the repository that owns each change.

## Coordinate Focused Skills

- Use `github-issue-planning` for native blockers, milestones, labels, and
  release-capstone metadata.
- Use `project-tooling-review` when implementing or auditing Just, CI, pins,
  Semgrep, uv, or repository-rule changes.
- Use the relevant Rust or Python build-portability skill for dependency,
  packaging, MSRV, or lockfile changes.
- Use `praxis-research` only when the release decision affects the planned
  scientific experiment; do not make independent maintenance appear
  scientifically mandatory.

## Report The Train

Report:

- the current Rust boundary and evidence source;
- the publication DAG with exact planned versions discovered at runtime;
- each repository's retained release gates and deferred issues;
- tooling drift that must be reconciled, plus justified differences;
- which crates are code-ready, published, or still blocked;
- the next executable work item and the condition that unlocks the following
  publication.
