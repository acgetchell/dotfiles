---
name: rust-ecosystem-release-train
description: "Coordinate dependent Rust crate releases, registry publication order, shared-tooling alignment, and release readiness."
---

# Rust Ecosystem Release Train

Coordinate a Rust crate release train while preserving each repository's
ownership, scientific contracts, and publication safeguards.

Use [issue-planning-to-release](../issue-planning-to-release/SKILL.md) for the shared
scope, issue mapping, publication/adoption, validation-ownership, and authorization
contract. This skill adds Rust-specific coordination; it does not redefine those
policies.

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

## Enforce The Release Contract

- For the maintained ecosystem, synchronize releases at intentional stable Rust boundaries; for other trains, honor their stated release/MSRV policy.
- When the selected train's policy uses a stable Rust release as a public MSRV
  boundary, align each repository's manifest, pinned toolchain, Clippy MSRV,
  active documentation, and CI with that boundary before publishing its release.
- Apply the shared publication boundary to crates.io dependency resolution and
  publish in dependency order. Development and isolated upstream package fixtures
  may proceed in parallel within their authorized scope.
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

Extend the shared issue-mapped release plan with:

- the current Rust boundary and evidence source;
- the publication DAG with exact planned versions when established, and unresolved
  version decisions otherwise;
- tooling drift that must be reconciled, plus justified differences;
- Rust-specific MSRV, native feature/platform, and crate-artifact release gates.
