# Public Repository Contract

## Dependency Graph

| Repository | Published crate | Ecosystem role | Published dependencies in this train |
|---|---|---|---|
| `acgetchell/la-stack` | `la-stack` | Numerical linear algebra, robust scalar policy, and exact arithmetic support | None of the other three crates |
| `acgetchell/delaunay` | `delaunay` | Triangulation, predicates, topology, embedding validation, and bistellar operations | `la-stack`, normally with the crate's required exact-arithmetic feature contract |
| `acgetchell/markov-chain-monte-carlo` | `markov-chain-monte-carlo` | Generic MCMC and Metropolis-Hastings mechanics | Independent of `la-stack` and `delaunay` |
| `acgetchell/causal-triangulations` | `causal-triangulations` | CDT state, moves, actions, observables, and simulation integration | `delaunay` and `markov-chain-monte-carlo` |

Do not add private or unpublished repositories to this public reference.

## Shared Release Invariants

- Release at deliberate stable Rust boundaries and keep the four active MSRV
  declarations synchronized unless a documented compatibility reason prevents
  it.
- Publish upstream crates before updating downstream registry requirements.
- Use crates.io dependency requirements in committed manifests. Do not use Git
  URLs or paths to bridge the release train.
- Commit and validate `Cargo.lock` in every repository according to its existing
  library/reproducibility policy.
- Keep Rust crate version, Python support-package version, release metadata,
  citation metadata, generated changelog release, and documentation snippets
  consistent for each repository's publication.
- Treat every upstream publication as incomplete until crates.io resolution,
  package inspection, docs/release checks, and the immediate downstream smoke
  contract succeed.

## Repository Details

### la-stack

- Own numerical correctness and exact-arithmetic primitives used by Delaunay.
- Keep correctness-sensitive accumulation, error-bound, non-finite, and exact
  fallback contracts explicit when adopting compiler features.
- Maintain the broad shared repository-tooling baseline: Rust, Python support
  scripts, release/performance artifacts, Semgrep, shell/config linting, and
  benchmark validation.
- Publish first after a Rust boundary. Delaunay may not declare the new
  `la-stack` requirement until that version is available from crates.io.

### delaunay

- Own geometry, triangulation, topology, validation levels, reconstruction,
  predicates, and bistellar mutation contracts.
- Consume the published `la-stack` version and its required feature set.
- Preserve specialized benchmark, profiling, large-scale, paper, and geometry
  validation workflows; do not force these into smaller repositories.
- Validate public API and feature compatibility plus representative D=2 through
  D=5 behavior before publication.
- After publishing, validate the exact downstream Delaunay adapter path in
  causal-triangulations before declaring the handoff complete.

### markov-chain-monte-carlo

- Own generic samplers, Metropolis-Hastings accounting, proposal/target
  interfaces, diagnostics, telemetry, and generic checkpoint mechanics.
- Remain independent of CDT and triangulation details.
- Publish independently of `la-stack` and Delaunay after the stable Rust gate.
- Preserve the repository's intentionally smaller workflow surface while
  aligning shared validation, release, pinning, and artifact contracts.
- After publishing, validate causal-triangulations with the registry version
  and its required features.

### causal-triangulations

- Own CDT domain invariants, geometry and MCMC adapters, simulation workflows,
  observables, and scientific release evidence.
- Consume only published crates.io versions of Delaunay and
  markov-chain-monte-carlo.
- Publish last in this four-repository train.
- Require downstream validation of both dependency adapters, exact checkpoint
  restoration where applicable, simulations, examples, doctests, slow
  scientific tests, performance evidence, and package inspection.
- Keep CDT-specific performance, notebooks, allocation checks, and simulation
  workflows as deliberate specializations rather than forcing them upstream.

## Dynamic State To Rediscover

Never rely on this reference for current values. Read them at planning time:

- current and proposed crate versions;
- current stable Rust release and scheduled next release;
- active milestone names and issue membership;
- latest crates.io and GitHub releases;
- dependency versions and feature flags;
- tool, action, Cargo, and uv pins;
- workflow matrices and repository rules.
