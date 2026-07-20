# Rust Changed-File Routing

Use this matrix after inspecting the scoped diff. Repository guidance overrides generic commands.

## Contents

- [Scope detection](#scope-detection)
- [Individual skill selection](#individual-skill-selection)
- [Focused validators](#focused-validators)
- [Full-CI escalation](#full-ci-escalation)
- [Handoff evidence](#handoff-evidence)

## Scope Detection

Use read-only git commands. For staged-only work, add `--cached`.

Classify effects rather than routing only by extension:

- source/API: `src/**/*.rs`, public modules, generated Rust, FFI
- tests: `tests/**`, unit modules, doctests, fuzz, compile-fail fixtures
- examples/benches: `examples/**`, `benches/**`, scientific fixtures
- build/package: `Cargo.toml`, `Cargo.lock`, `.cargo/**`, `build.rs`, toolchain and lint files
- docs/tooling: README/docs, workflows, `justfile`, configuration

## Individual Skill Selection

| Changed contract | Select |
|---|---|
| `cfg`, features in source, MSRV compilation, targets, `build.rs`, generated code, proc macros, cross-compilation, `no_std`, WASM, FFI/linking, external consumers | `rust-build-portability` |
| Manifest dependencies/features, workspace inheritance, lockfile policy, edition/MSRV declaration, lint tables, package metadata, publishing | `rust-cargo-hygiene` |
| New/changed public item documentation, required Errors/Panics/Safety/Examples sections, intra-doc links, docs.rs rendering | `rust-api-docs` |
| Prelude, `pub use`, visibility, feature-gated exports, downstream imports | `rust-prelude-exports` |
| Builder, proposal, transaction, guard, staged workflow, chaining, duplicate fluent surface | `rust-fluent-api-design` |
| Generic bounds, associated types, HRTBs, callable traits, `impl Trait`, generic diagnostics | `rust-trait-bounds` |
| CLI packaging, clap/argument boundary, process output/exit behavior, CLI docs | `rust-cli-design` |
| Coordinated mutation, state machine, cache/index update, rollback, topology edit, failure atomicity, inverse sequence | `rust-invariant-state-transitions` |
| Smart constructor, raw DTO, parser, deserialization, refined type, setter, invalid stored state | `rust-parse-dont-validate` |
| Error enum/category, conversion, `Result` propagation, structured diagnostic context | `rust-error-variants` |
| Snapshot, clone/cache, canonical owner, handle provenance, lifetime-bound view or transaction shape | `rust-borrowed-view-audit` |
| Formula, numerical/geometry/topology behavior, tolerance, exactness, stochastic semantics, scientific claim | `rust-scientific-correctness` |
| Async, threads, locks, channels, atomics, Send/Sync, blocking, scheduling, cancellation | `rust-concurrency-async` |
| Naming, imports, or path clarity | `rust-style-hygiene` |
| Iterator/loop/closure/pattern/exhaustiveness or control-flow allocation | `rust-iter-control-flow` |
| Deletion, deduplication, redundant helper/test/API, accidental complexity | `rust-simplification-review` |
| Hot path, allocation, data movement, complexity, benchmarked optimization | `rust-invariant-performance` |
| Behavioral tests, doctests as evidence, property/fuzz/compile-fail/concurrency tests, regressions | `rust-test-quality` |

Always add `rust-production-review` last for orchestrated final synthesis. Do not load unrelated skills from the same group.

Route workflow/config-only mechanics to `project-tooling-review` when no Rust semantic contract changes.

## Focused Validators

Use documented repository commands first. Generic fallbacks are examples, not mandatory new tooling.

| Risk | Focused evidence |
|---|---|
| Core Rust behavior | affected package/test target; fallback `cargo test --lib` and focused Clippy |
| Public API/docs | doctests, `cargo doc` with rustdoc warnings denied, representative downstream consumer |
| Feature/target/MSRV | affected no-default/all/curated features, declared MSRV, target checks, external consumer |
| State transition/rollback | focused success/rejection/failure-injection and operation-sequence tests |
| Error contract | exact variant/field tests and affected public callers |
| Scientific behavior | known-value, property, adversarial, independent-oracle, feature/backend parity tests |
| Async/concurrency | deterministic synchronization tests; Loom/model checks when established; runtime-specific tests |
| Iterator/simplification/style | focused tests plus format/Clippy for the touched package |
| Performance | same representative benchmark or allocation proxy before and after, after correctness passes |
| Tests only | narrow named test, doctest, property replay, fuzz regression, or compile-fail target |
| Cargo/package | manifest checks, feature checks, package/publish dry run when release scope requires it |
| Workflows/YAML/docs | repository tooling, action, YAML, Markdown, or link validators |

If `benches/README.md` exists and performance or benchmark fixtures are in scope, read it before selecting benchmark commands.

Before running a validator, record the source/build state, toolchain, target,
features, instrumentation, and exact test selection in the orchestrator's
validation ledger. Reuse a still-valid result from another skill. When a
validator fails, keep the failure in the current skill, repair caused failures
when authorized, rerun it after that repair invalidates the prior result, and
record genuine blockers before continuing.

## Full-CI Escalation

Run the repository full gate when required locally, when no smaller set covers cross-layer risk, when public API and core invariants change together, when topology/numerical/rollback behavior changes broadly, or when final synthesis finds uncovered integration risk.

Do not escalate solely because orchestration is ending. Focused evidence is normally sufficient for docs-only, config-only, tests-only, examples-only, or narrowly isolated changes.

Decide whether repository policy or known cross-layer scope requires the full
gate before executing the first test, and inspect the gate's composition then.
If it contains tests already passing for the current
source/build/configuration state, choose the full gate as the single test
selection from the outset or run only its uncovered validators. Do not run a
named test, its containing target or package, the workspace suite, and full CI
as nested tiers. If a mandatory indivisible gate is discovered late and offers
no reliable exclusion, report the command-surface blocker and route it to
`project-tooling-review`; do not silently replay tests or count them twice. A
relevant edit invalidates earlier evidence; a request for a broader summary
does not.

## Handoff Evidence

Report:

- scoped files and effects
- each selected and meaningful skipped individual skill
- exact skill and reference files loaded
- findings, fixes, and per-skill validators
- the shared validation ledger, including any justified reruns
- final synthesis verdict and residual risk
- git-state confirmation
