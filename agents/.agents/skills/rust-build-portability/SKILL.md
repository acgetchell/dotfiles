---
name: rust-build-portability
description: "Audit and fix Rust build-boundary correctness across MSRV and stable toolchains, Cargo features, target triples, cfg-selected APIs and behavior, build scripts, generated code, proc macros, dependency feature unification, no_std or alloc modes, WASM, FFI and native linking, and downstream consumers. Use when source or build changes are feature-, target-, platform-, architecture-, linker-, environment-, or toolchain-sensitive."
---

# Rust Build Portability

Audit whether every supported Rust configuration builds the same intended crate contract. Treat MSRV, features, targets, generated artifacts, and downstream consumption as correctness boundaries rather than CI decoration.

## Ground Rules

- Read repository-local toolchain, feature, platform, and publishing guidance first.
- Reconstruct the declared support matrix before recommending expansion or removal.
- Keep manifest metadata, dependency declaration style, lint tables, and release packaging under `rust-cargo-hygiene`; keep workflow, recipe, cache, and runner mechanics under `project-tooling-review`.
- Keep caller-facing API design under the appropriate surface skill and durable compile-contract evidence under `rust-test-quality`.
- Verify version-sensitive Rust, Cargo, target, and dependency behavior from authoritative sources when currentness matters.
- Do not mutate git state unless explicitly requested.

## Workflow

### 1. Establish the supported matrix

Record:

- edition, declared MSRV, pinned contributor toolchain, and stable/nightly policy
- workspace resolver and published versus internal crates
- default, minimal, all-feature, and curated feature combinations
- supported target triples, operating systems, architectures, runtimes, and link modes
- `std`, `alloc`, `no_std`, WASM, embedded, FFI, or native-library promises
- build scripts, proc macros, generated bindings/configuration, and native dependencies

Do not infer support from a workflow file alone. Separate declared support, locally demonstrated cells, CI-only evidence, and aspirational configurations.

### 2. Audit feature and `cfg` agreement

Check:

- features are additive unless an explicit mutually exclusive contract is enforced
- `#[cfg]`, `cfg!`, `cfg_attr`, module declarations, re-exports, docs, examples, and tests agree
- every supported combination exposes a coherent public API and error behavior
- target or feature selection cannot change a public type's meaning across cooperating crates without an explicit package/API boundary
- optional dependencies use `dep:` activation deliberately and do not leak through dev or transitive features
- Cargo feature unification cannot silently enable behavior a crate assumes is disabled
- mutually exclusive backends fail early with an actionable compile error rather than ambiguous definitions

Treat source-level feature semantics as this skill's responsibility even when `Cargo.toml` itself did not change.

### 3. Audit MSRV and compiler behavior

Check that syntax, standard-library APIs, Cargo features, proc-macro expansions, dependencies, and generated code compile under the declared MSRV. A current stable build does not prove MSRV support.

Flag:

- accidental edition or unstable-feature dependence
- dependency resolution that raises MSRV without an explicit policy decision
- build scripts or proc macros using newer facilities than the consuming crate
- rustdoc, doctest, test, or example paths that require a newer compiler than normal library compilation

Route declaration and semver policy for an MSRV bump to `rust-cargo-hygiene`; this pass proves the matrix behavior.

### 4. Audit targets, build scripts, and generated artifacts

Check:

- target-specific dependencies and `cfg` predicates use the intended target vocabulary
- host-built build scripts and proc macros do not confuse host and target properties during cross-compilation
- `build.rs` emits precise `rerun-if-changed`, `rerun-if-env-changed`, link, and `rustc-cfg` directives
- custom cfg names are declared for check-cfg validation
- generated files are deterministic, correctly invalidated, and written only to appropriate output locations
- environment discovery has an explicit fallback or actionable error
- native libraries, C/C++ runtimes, link search paths, symbol visibility, and runtime loading match every supported platform
- path, endianness, pointer width, alignment, atomic availability, filesystem, and process assumptions are target-safe

Do not add platform branches before minimizing the actual language, dependency, linker, or environment difference.

### 5. Audit constrained environments and consumers

When relevant, verify:

- `no_std` and `alloc` boundaries do not import `std` indirectly
- panic, allocator, threading, time, randomness, filesystem, and networking assumptions match the target
- WASM APIs distinguish browser, WASI, and host-JavaScript contracts
- FFI types, calling conventions, panic containment, ownership, and native link requirements are explicit
- installed or published crates build from an external consumer without workspace-only features, paths, generated files, or dev dependencies

Use a public consumer or packaged-source build when workspace context could hide missing requirements.

### 6. Check configuration-sensitive behavior

Compare debug/release, overflow checks, panic strategy, LTO, codegen units, tests, docs, and feature/target variants when they can alter observable correctness. Validation reachable from ordinary input must not disappear only because debug assertions are disabled.

## Validation

Record portability evidence in the parent orchestrator's shared validation
ledger when supplied; otherwise create the same ledger locally. Key each result
by source/build state, toolchain, target, features, instrumentation, and exact
test selections. Reuse a matching matrix cell instead of executing it again.

Choose only affected matrix cells, using repository commands when available. Typical evidence includes:

1. default and no-default-feature builds
2. all features plus curated non-default combinations
3. declared MSRV and current stable toolchains
4. affected target triples or cross-compilation checks
5. external downstream consumers, examples, doctests, and packaged-source builds
6. build-script regeneration and clean/repeated-build determinism
7. `no_std`, WASM, native-link, static/dynamic, or panic-strategy variants when supported
8. feature powerset tooling such as `cargo hack` only when already available or justified by repository policy

Do not claim the full matrix from one host build. Record exact toolchains, targets, features, commands, results, and unavailable cells.

## Finding Standard

For each finding, name the affected toolchain, target, feature set, crate, generated artifact, or consumer; show the compile, link, API, or behavioral failure; identify the violated support contract; and give the smallest portable correction plus focused validation.

## Handoff

Summarize the declared and demonstrated matrix, cfg and feature contracts,
build scripts and consumers inspected, validators, unavailable cells, work
routed to Cargo hygiene or project tooling, files changed, and confirmation
that no git state mutation occurred when true. Include the ledger's
source/build state, toolchain, target, features, instrumentation, and exact
test selections, or explicitly confirm that the parent orchestrator recorded
those fields.
