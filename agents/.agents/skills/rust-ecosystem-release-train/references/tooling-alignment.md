# Tooling Alignment Contract

## Alignment Principle

Synchronize behavior, safety guarantees, and operator vocabulary where the
repositories share a need. Do not require byte-identical files. A difference is
acceptable when it follows from crate features, platforms, artifacts, runtime,
or scientific responsibilities; document the reason during the comparison.

## Justfiles And Tool Pins

All four repositories use a `justfile` as the canonical operator interface.
Compare shared recipe families and their dependency composition, especially:

- `setup`, `check`, `check-fast`, `fix`, `ci`, and any slow CI lane;
- Rust formatting, Clippy, docs, tests, examples, benches, coverage, and package
  or publish checks;
- Python sync, formatting, linting, typing, and tests;
- TOML, YAML, Markdown, shell, JSON, spelling, action linting, and Zizmor;
- Semgrep scan and fixture validation;
- changelog, tag, release, performance, and artifact workflows.

Compare shared pins for Cargo tools and repository tools such as nextest,
llvm-cov, machete, Clippy SARIF, dprint, git-cliff, Just, rumdl, SARIF formatters,
Taplo, typos, uv, and Zizmor. Preserve specialized pins such as Delaunay's
profilers/paper tools or repository-specific security tools only where needed.

When a pin moves, update every applicable repository deliberately, run the
owning validators, and record exclusions. Do not assume the numerically largest
pin is compatible everywhere.

## GitHub Actions And Repository Automation

The shared workflow spine includes CI, Rust Clippy/SARIF, CodeQL, Codecov,
Semgrep SARIF, audit, Zizmor, and Dependabot auto-merge. Release and benchmark
workflows vary by repository.

Compare:

- immutable action SHAs and their version comments;
- minimal `permissions`, trigger filters, concurrency, timeouts, and matrices;
- Rust, Python, uv, and Just setup behavior;
- cache keys and lockfile inputs;
- artifact names, retention, provenance, and publication boundaries;
- secrets usage and fork/pull-request safety;
- Dependabot ecosystems, directories, cadence, grouping, and auto-merge policy.

Keep Delaunay-specific paper/profiling/baseline workflows and
causal-triangulations-specific simulation/performance workflows specialized.
Align their shared action and security foundations anyway.

## Cargo And Rust

For every stable Rust boundary:

1. Read the final Rust, Cargo, Clippy, rustfmt, and rustdoc notes.
2. Align `Cargo.toml` `rust-version`, `rust-toolchain.toml`, `clippy.toml`, CI,
   contributor docs, and release docs.
3. Audit applicable language/library/tooling changes per repository rather than
   adopting new APIs speculatively.
4. Update direct and transitive dependencies intentionally; inspect feature and
   MSRV changes and regenerate locks through normal Cargo commands.
5. Publish in dependency order and update downstream manifests only after the
   upstream registry release resolves.
6. Run default/all-feature checks, package/publish checks, docs, examples,
   benchmarks, and repository-specific slow or scientific validation.

Do not rewrite archived provenance or historical fixtures merely because they
record an older toolchain.

## Python And uv

All four repositories maintain Python support tooling through `pyproject.toml`
and `uv.lock`; most also pin `.python-version`. Keep these aligned where their
support surfaces overlap:

- Python baseline and classifiers;
- support-package version versus Rust crate version;
- build backend and package metadata;
- exact dev-tool pins for actionlint, pytest, Ruff, Semgrep, shell tools, ty,
  and YAML/Markdown tooling as applicable;
- notebook groups only in repositories that own notebooks;
- security overrides with an issue or comment explaining when removal is safe;
- Ruff, pytest, typing, formatting, and package-build contracts.

Use `uv lock`, inspect the resolved change, and run the repository's Python and
package validators. Do not copy a dependency group into a repository that does
not use that tool or artifact class.

## Semgrep

All four repositories own a root `semgrep.yaml`, Semgrep CI integration, and
repository fixtures. Align reusable policy for:

- GitHub Action pinning and workflow safety;
- command ordering and repository validation contracts;
- Rust panic, erased-error, import-boundary, and API policy where applicable;
- Python exception and parse-boundary behavior;
- public examples, doctests, benchmarks, and documentation surfaces;
- fixture result shape, rule ID, source line/span, and diagnostic validation.

Every shared rule change must include receiving-repository fixtures and pass
both the fixture validator and full Semgrep scan. Keep geometry, numerical,
topology, CDT, paper, notebook, and other domain-specific rules in their owning
repositories.

## Alignment Report

For each repository and surface, classify the result as:

- **aligned**: same contract and compatible pins;
- **update required**: shared contract applies and drift is unjustified;
- **intentionally specialized**: difference is required and explained;
- **not applicable**: repository lacks the relevant feature or artifact;
- **blocked**: an upstream release, tool compatibility issue, or security
  constraint prevents alignment.

Never hide drift by calling it specialization without a concrete repository
reason.
