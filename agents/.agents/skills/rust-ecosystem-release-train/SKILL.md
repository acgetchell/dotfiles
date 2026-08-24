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

## Authorization Boundary

Release planning and readiness assessment are read-only by default. Inspect
repository files, GitHub metadata, crates.io state, and official Rust sources,
but do not stage, commit, push, tag, checkout, reset, stash, create, edit, move,
close, or publish issues, milestones, dependency links, releases, repository
content, or crates without explicit user authorization in the current turn.
Explicit authorization for these mutating operations is required before execution,
including all existing repo and publication mutations.

Before requesting authorization, preview the exact issues, milestones,
dependency relationships, release records, repository edits, and publication
steps intended for each repository. Authorization to plan or assess readiness
does not authorize external or repository mutation, and publication requires
explicit authorization even when the rest of the train is already approved.

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
  overrides, and support-package behavior; route any discovered repository edits on
  these Python surfaces through `python-review-orchestrator` in orchestrated mode
  and include `python-production-review` synthesis in the evidence chain before
  declaring release readiness.
- Python support-package versions, release/citation metadata, generated changelog
  fragments, and documentation version snippets, validating against the shared
  invariants in [`references/repositories.md`](references/repositories.md)
- `semgrep.yaml`, repository-owned rules, fixtures, fixture validators, and
  Semgrep CI integration.

After any release publication, perform post-publication package inspection and
documentation/release verification for affected repositories with explicit evidence
for each check before declaring a crate release-ready.

Prefer repository files and native GitHub metadata over issue-body prose. Use
official Rust release sources for schedules and final release notes.

## Build The Release Plan

1. Identify or propose one Rust-adoption issue and one release-capstone issue
   for each participating release; create them only after authorization.
2. Treat a release milestone as a publication contract. Review every open item;
   keep genuine release gates and move unrelated work rather than silently
   delaying the train.
3. Make each release capstone blocked by all retained local gates and by the
   release capstone of each upstream crate it consumes.
4. Make downstream integration work depend on the upstream **published-release
   capstone**, not merely on the implementation issue that introduced an API.
5. Work bottom-up. Before each publication, explicit authorization is required for
   any mutation, including moving work items, adding dependency links, publishing
   or closing issues, and updating any downstream Cargo or lockfile state. When
   missing, emit reviewable proposals instead of applying direct changes.
6. Work bottom-up. After each publication, update downstream Cargo
   requirements/locks through the registry, then run downstream contract
   validation; only execute those updates with explicit authorization.
7. Keep the final ecosystem capstone open until the published crates resolve
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
- Use `python-review-orchestrator` in orchestrated mode for dependency,
  packaging, release-surface, or lockfile work touching `pyproject.toml`, `uv.lock`,
  support-package behavior, or other Python-owned surfaces; require an accepted
  `python-production-review` synthesis pass before finalizing those release-ready
  decisions.

## Report The Train

Report:

- the current Rust boundary and evidence source;
- the publication DAG with exact planned versions discovered at runtime;
- each repository's retained release gates and deferred issues;
- tooling drift that must be reconciled, plus justified differences;
- which crates are code-ready, published, or still blocked;
- the next executable work item and the condition that unlocks the following
  publication.
