---
name: rust-test-quality
description: "Review Rust unit, integration, doctest, property, fuzz, compile-fail, Miri, sanitizer, concurrency-model, benchmark-fixture, and example tests for meaningful risk coverage, precise assertions, deterministic reproduction, and reliable failure diagnostics. Use when tests change or production behavior needs durable regression evidence."
---

# Rust Test Quality

Review Rust tests as executable evidence for behavior, invariants, compatibility, and safety. Strengthen tests that can pass while the target behavior is wrong.

## Ground Rules

- Follow repository-local frameworks, fixture placement, feature policy, commands, and diagnostic tooling.
- Default to changed tests plus the production risk they claim to cover.
- Keep public documentation completeness under `rust-api-docs`, source build-matrix correctness under `rust-build-portability`, and test/CI wiring under `project-tooling-review`.
- Do not require one doctest per public function. Require runnable examples for non-trivial public workflows and semver-relevant contracts where copied usage provides real evidence.
- Do not add a property, fuzz, compile-fail, Miri, Loom, or sanitizer framework merely for ceremony; use established tooling or add it only when the uncovered risk justifies the maintenance cost.
- Do not mutate git state without explicit authorization.

## Workflow

### 1. Identify the failure the test must detect

For each changed behavior, name the incorrect implementation, invariant violation, compatibility break, panic, race, or scientific error the test should catch.

Reject tests that only execute code, check `is_ok()`/`is_err()`, assert a generic validity helper, or duplicate production logic as the oracle. Prefer exact outputs, state deltas, typed error variants and fields, independent properties, and observable public behavior.

### 2. Choose the right evidence level

Use:

- unit tests for local algorithms and private invariants
- integration tests for public package behavior and module boundaries
- doctests/examples for realistic downstream usage and import paths
- property or metamorphic tests for broad invariant-bearing input spaces
- fuzzing for parsers, serialization, unsafe boundaries, state machines, and complex mutation sequences
- compile-fail or `trybuild` tests for stable type, trait-bound, lifetime, macro, and misuse contracts
- model checking such as Loom for concurrency interleavings when established and warranted
- benchmarks only as performance evidence after correctness is asserted outside measured work

Avoid using an expensive or brittle layer when a focused deterministic regression proves the same risk.

### 3. Cover success, rejection, and failure atomicity

Check:

- smallest successful examples and exact expected results
- empty, boundary, malformed, unsupported, overflow-adjacent, non-finite, and degenerate inputs where relevant
- every meaningful typed rejection category
- public recoverable inputs return `Err`/`None` rather than panic
- failed setters, builders, transactions, repairs, and restores leave promised state unchanged
- operation sequences, inverse behavior, retry, drop rollback, and cache/index consistency
- a regression test exists for each fixed defect

Use panic tests only when panic is the deliberate public or internal contract. Do not normalize recoverable public panic behavior by testing it as success.

### 4. Make assertions independent and diagnostic

Prefer:

- direct equality or structured field assertions
- exact error variants plus relevant context
- analytical values, exact arithmetic, trusted independent implementations, or metamorphic properties
- canonical snapshots only when representation stability is part of the contract
- multiple nonfatal assertions when independent postconditions should all be reported

Avoid matching complete error prose, debug formatting, nondeterministic iteration order, or incidental storage layout unless explicitly promised.

### 5. Keep generated and stochastic evidence reproducible

Record failing seeds and minimize counterexamples. Keep generators within the intended domain unless testing rejection. Preserve discovered failures as deterministic regressions.

For scientific or numerical behavior, cover supported dimensions/features and adversarial regimes with an oracle independent of the production path. Defer mathematical validity to `rust-scientific-correctness` while ensuring the test harness preserves its evidence.

### 6. Test compile and configuration contracts

When public generics, macros, features, cfg-selected APIs, targets, MSRV, or downstream usage changes, check:

- minimal external consumers use only published paths and dependencies
- compile-pass cases exercise intended bounds, lifetimes, conversions, macros, and feature combinations
- compile-fail cases reject dangerous uses through stable categories rather than complete compiler prose
- default, no-default, all, and affected curated feature sets receive appropriate evidence
- doctests/examples do not compile only because of workspace, dev-dependency, or hidden feature context

`rust-build-portability` owns which configurations must build; this skill owns whether durable tests detect regression.

### 7. Test concurrency and unsafe boundaries proportionately

For concurrency, avoid timing-only sleeps; use barriers, channels, deterministic scheduling hooks, or model checking. Assert cancellation, shutdown, join/error propagation, and state consistency.

For unsafe/FFI or aliasing-sensitive code, use targeted regression tests and established Miri, sanitizer, or platform checks where they can exercise the actual assumption. A clean dynamic run supplements rather than proves soundness.

### 8. Check harness reliability

Verify:

- test discovery includes every intended case
- feature and cfg gates do not silently remove critical tests
- ignored tests have documented ownership and execution paths
- fixtures clean up and avoid order dependence
- expected-failure tests fail when the expected condition disappears
- fuzz/property regressions replay in ordinary validation when practical
- benchmark setup and correctness checks remain outside measured closures
- nonzero exits and diagnostic reports propagate through repository commands

## Validation

Maintain a validation ledger keyed by the relevant source state, built artifact,
toolchain, target, feature set, profile, instrumentation, and exact test
selection. Before executing a repository recipe or Cargo command, inspect what
it selects, decide whether repository policy or the known scope requires an
indivisible full gate, and reuse still-valid evidence already in the ledger.

Choose the smallest single test selection that proves the touched risk: a named
test, doctest, property replay, fuzz regression, compile-fail target, model
check, affected package, or feature tier. Do not run a named test and then its
containing target, package, workspace, and full CI as successive tiers. If a
broader gate is independently required, choose it initially or run only the
portion not already recorded as passing.

If an indivisible policy-mandated gate is discovered only after overlapping
tests have passed and it offers no reliable exclusion, report the validation
and command-surface conflict and route it to `project-tooling-review`; do not
silently replay the tests or count the duplicate execution as new evidence.

Rerun a test only after relevant source, fixture, build, or configuration
changes invalidate its result, or when diagnosing nondeterminism. A different
toolchain, target, feature set, Miri/sanitizer mode, or other material runtime
configuration is distinct evidence rather than a duplicate. Repeated
property, fuzz, concurrency, or benchmark samples are also distinct when the
repetition is itself part of the stated test design; record the seed, schedule,
or sample purpose.

## Finding Standard

For each finding, state what wrong implementation could still pass, the missing input/oracle/assertion/configuration, the smallest stronger test, and the command that demonstrates it.

## Handoff

Summarize risks and tests inspected, evidence strengthened, independent oracles, seeds/counterexamples, compile/configuration contracts, the non-overlapping validation ledger, remaining gaps, files changed, and confirmation that no git state mutation occurred when true.
