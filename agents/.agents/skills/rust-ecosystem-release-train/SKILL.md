---
name: rust-ecosystem-release-train
description: "Coordinate dependent Rust crate releases, registry publication order, shared-tooling alignment, and release readiness."
---

# Rust Ecosystem Release Train

Coordinate a Rust crate release train while preserving each repository's
ownership, scientific contracts, and publication safeguards.

## Load The Ecosystem Contract

Select by release activity, without a repository allowlist or required profile.
For the maintained la-stack/delaunay/MCMC/causal-triangulations train, read
[repository contracts](references/repositories.md). For another train, derive its
dependency graph and release policy from the supplied manifests and registry.

- For planning, readiness, or authorized publication, read
  [release planning](references/release-planning.md).
- For shared tooling or dependency alignment, read
  [alignment](references/shared-alignment.md) and
  [tooling contracts](references/tooling-alignment.md) where applicable.

Exclude private or unpublished repositories from this public skill. Do not
infer or expose their names, dependencies, issues, or release plans.

## Authorization Boundary

Release planning and readiness assessment are read-only by default. Inspect
repository files, GitHub metadata, crates.io state, and official Rust sources,
but do not stage, commit, push, tag, checkout, reset, stash, create, edit, move,
close, or publish issues, milestones, dependency links, releases, repository
content, or crates without explicit user authorization for that operation and scope.
Explicit authorization for these mutating operations is required before execution,
including all existing repo and publication mutations.

Honor existing explicit authorization for the same action and scope. When
additional authorization is needed, first preview the exact issues, milestones,
dependency relationships, release records, repository edits, and publication
steps intended for each repository. Authorization to plan or assess readiness
does not authorize external or repository mutation, and publication requires
explicit authorization even when the rest of the train is already approved.

## Enforce The Release Contract

- For the maintained ecosystem, synchronize releases at intentional stable Rust boundaries; for other trains, honor their stated release/MSRV policy.
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

For the maintained ecosystem, verify this publication graph against current manifests:

```text
stable Rust ─→ la-stack ─→ delaunay ───────────────┐
          └─→ markov-chain-monte-carlo ────────────┤
                                                    └─→ causal-triangulations
```

`la-stack` and `markov-chain-monte-carlo` may publish in parallel after the
Rust boundary. `delaunay` must consume the published `la-stack` release.
`causal-triangulations` must consume the published `delaunay` and
`markov-chain-monte-carlo` releases.

## Report The Train

Report:

- the current Rust boundary and evidence source;
- the publication DAG with exact planned versions discovered at runtime;
- each repository's retained release gates and deferred issues;
- tooling drift that must be reconciled, plus justified differences;
- which crates are code-ready, published, or still blocked;
- the next executable work item and the condition that unlocks the following
  publication.
