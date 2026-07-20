---
name: cpp-review-orchestrator
description: "Coordinate C++23 reviews using the CDT++-oriented CMake/CMakePresets, vcpkg manifest, doctest/CTest, just, Semgrep, clang-format, and clang-tidy toolchain across build portability, ownership, invariants, parsing, exception safety, API design/docs, functional composition, scientific correctness, concurrency, tests, and final synthesis. Use for changed C++ source, headers, modules, API comments, Doxygen, tests, builds, dependencies, diagnostics, or multi-concern review work."
---

# C++ Review Orchestrator

Coordinate focused C++ review skills without copying their content. Load selected skills in logical pass groups, record actionable issues, apply fixes only when the user requested them, validate the touched surface after each group, and finish with the existing broad production review as synthesis.

The intent is to replace a maintainer manually invoking several C++ reviews. Do not collapse build-portability, lifetime, invariant, parsing, exception, API-design, API-documentation, functional, scientific, concurrency, testing, and synthesis concerns into one blended pass and report it as orchestrated work.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Use read-only git commands to discover scope when needed.
- Use C++23, target-based CMake with checked-in presets, vcpkg manifest mode, doctest through CTest, `just` recipes, Semgrep, clang-format, and clang-tidy. Do not introduce parallel C++ toolchains unless the user explicitly requests one.
- Respect repository-local instructions and exact recipe/preset names plus documented compiler, standard-library, triplet, dependency, and sanitizer support.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for a repository-wide or baseline audit.
- When invoked by `repo-review`, honor its handed-off branch file list, diff, or baseline inventory instead of rediscovering a narrower scope.
- When the user asks to fix issues, implement actionable findings as each group discovers them unless the fix is blocked or unsafe.
- Select focused validators from touched risks. Do not run full CI by default.
- Maintain one cross-group validation ledger. Reuse still-valid results and never rerun the same test selection under the same source/build/configuration state.

## Review Trace

When invoked by `repo-review`, begin with a handoff receipt naming the C++ scope, selected and skipped groups with reasons, and routing files to load.

For each selected specialist group and the mandatory final synthesis, announce the group and focused skills before loading them. A group is complete only when the final summary can name its status, skill files loaded, files inspected, findings or explicit no-finding result, fixes, and focused validators. A remembered skill name or one blanket CI run is not grouped evidence.

Provide table-ready evidence to the parent: selected groups, loaded skills and references, validators, fixes, and intentionally skipped groups.

## Required Skill Loading

Load every selected specialist skill's `SKILL.md` completely at the start of its logical group and follow directly relevant references. Always load `cpp-production-review` for mandatory final synthesis after the specialist groups. Use the [Per-Group Fix Loop](#per-group-fix-loop) as the execution procedure.

## Scope Routing

Read [`references/check-routing.md`](references/check-routing.md) after identifying the C++ scope. Use it to choose groups, focused validators, and whether final validation must escalate.

For CDT++ or closely related C++ causal-dynamical-triangulation and CGAL work, load repository context progressively after the general routing matrix:

- Always read [`references/cdt-plusplus.md`](references/cdt-plusplus.md) for compact sources-of-truth and cross-group policy.
- Read [`references/cdt-build-portability.md`](references/cdt-build-portability.md) only when Build and Portability Contract is selected.
- Read [`references/cdt-scientific-topology.md`](references/cdt-scientific-topology.md) only when scope touches CGAL handles or triangulations, topology moves, numerical predicates, causal structure, randomness, or simulation behavior.
- Read [`references/cdt-test-diagnostics.md`](references/cdt-test-diagnostics.md) only when Validation and Test Quality is selected or test registration, sanitizer coverage, or diagnostic behavior changes.

If files do not match the routing table cleanly, choose the smallest pass set that covers the risk and state the assumption.

## Skill Groups

Run selected specialist groups in this order, then always run Final Synthesis.

### 1. Build and Portability Contract

Use when changes affect public headers, translation-unit boundaries, C++ standard enforcement, compiler or standard-library support, ODR or linkage, templates or explicit instantiation, modules, generated configuration headers, symbol visibility, static/shared builds, target compile features/definitions/options, exception/RTTI/assertion modes, PCH, unity builds, LTO, or supported platform configurations.

- `cpp-build-portability`

Run this first when applicable so later groups use the actual language, CMake target/preset, vcpkg, macro, dependency, and configuration contract. This pass owns whether supported builds compile and link the same intended C++ program; route `just` recipe ergonomics, workflow wiring, Semgrep/Clang configuration mechanics, and tool pins to `project-tooling-review`.

### 2. Lifetime and Ownership Safety

Use when source or headers affect RAII, resources, pointers, references, views, spans, iterators, handles, callbacks, coroutines, promises, awaiters, suspension points, container or topology mutation, C interfaces, or exception cleanup.

- `cpp-lifetime-ownership-safety`

Run this before invariant review when later reasoning depends on safe handles or borrows.

### 3. Invariant and State Transitions

Use for construction, validation, mutation, caches, coordinated fields, graph or topology operations, state machines, rollback, inverse operations, and failure atomicity.

- `cpp-invariant-state-transitions`

Do not require parse-don't-validate or a broad API redesign. Architecture is in scope only when needed for a verified correctness fix.

### 4. Boundary Parsing and Invalid-State Prevention

Use when raw external representations cross into invariant-bearing code through constructors, factories, builders, parsing, deserialization, configuration, checked numeric conversion, public aggregates, or setters, especially when later code repeats validation or can still store invalid values.

- `cpp-parse-dont-validate`

Keep coordinated mutation and failure atomicity in Invariant/State. Select this group for the boundary and type design that preserves validation evidence inward; do not require refined wrappers for passive DTOs or local values with no meaningful invariant.

### 5. Exception Safety and Error Contracts

Use for `throw`, `try`, `catch`, `noexcept`, exception guarantees, `std::expected`, `std::error_code`, result/status/optional returns, constructors, destructors, move construction or assignment, assertions, termination, rollback or transaction-style updates, parsing, serialization, filesystem, networking, callbacks, plugin interfaces, C interoperability, ABI boundaries, and operations that may fail after mutation begins.

- `cpp-exception-safety-error-contracts`

Keep resource lifetime analysis in Lifetime/Ownership and final object-state invariants in Invariant/State; this pass owns the error contract and its propagation.

### 6. Public API and Type Design

Use when public or cross-module headers, modules, signatures, exported types, constructors, conversions, overload sets, templates, concepts, deduction guides, customization points, builders, fluent APIs, virtual interfaces, symbol visibility, exposed layout, or downstream consumer ergonomics change.

- `cpp-api-design`

Run after ownership, invariant, parsing, and error-contract groups when those concerns determine what the public signature must express. This pass owns caller usability, generic constraints, overload behavior, compatibility, and API/ABI exposure rather than redoing implementation correctness.

### 7. Public API Documentation

Use when public comments, Doxygen or related configuration/output, headers or modules as rendered documentation, canonical examples, or caller-facing API guides change, and when a changed public contract requires documentation synchronization.

- `cpp-api-docs`

Run after API Design and specialized contract owners establish technical truth. Reuse complete `cpp-api-docs` evidence from a documentation orchestrator pass for the same scope rather than rerunning it, and record the skill as selected with reused evidence.

### 8. Functional Composition and Control Flow

Use when changed code centers on standard algorithms, ranges or lazy views, transformation pipelines, folds, higher-order functions, lambda capture, `optional`/`expected`/`variant` composition, controlled effects, or a substantial loop-versus-pipeline refactor.

- `cpp-functional-style`

Select this group for material data-flow, lifetime, allocation, ordering, or error-composition questions, not merely because a file contains a lambda or `std::ranges` call. Hand dedicated ownership, error, numerical, and concurrency risks to their owning groups.

### 9. Scientific Correctness

Use when numerical, geometric, combinatorial, stochastic, simulation, scientific fixture, or research-facing behavior is affected.

- `cpp-scientific-correctness`

This pass establishes model validity before performance or cleanup. Rerun affected scientific checks if later fixes alter formulas, predicates, arithmetic order, tolerances, RNG semantics, topology, or fixtures.

### 10. Concurrency and Reentrancy

Use only when threads, TBB, OpenMP, standard parallel algorithms, tasks, locks, atomics, signal handlers, shared caches, global state, callbacks, or shared RNG state are affected.

- `cpp-concurrency-reentrancy`

### 11. Validation and Test Quality

Use for doctest scenarios/cases, CTest registration, fixtures, examples that assert behavior, sanitizer regressions, property/fuzz tests, and benchmark correctness fixtures. Also use whenever production C++ behavior changed enough to require regression evidence.

- `cpp-test-quality`

Project-tooling review owns workflow and command wiring; this group owns the semantic strength of the tests.

### 12. Final Synthesis

Run after every C++ review regardless of scope. This group is mandatory even when no earlier specialist group applies.

- `cpp-production-review`

Hand this pass the prior groups' evidence, including explicit skips. It must reconcile findings without rerunning completed specialist analysis, cover residual dependency/performance/simplification/integration concerns, remove duplicates, and classify every remaining risk or explicitly report that none remains.

## Per-Group Fix Loop

For each selected group:

1. Announce the group and skills.
2. Load every selected skill completely plus directly relevant references.
3. Inspect scoped files and nearby owners of the affected contract.
4. Apply the group as a focused review and record findings or an explicit no-finding result.
5. If the user requested fixes, implement the smallest safe correction for real findings; otherwise record remediation without editing.
6. Run the focused validator selected from the routing reference only for evidence not already present and valid in the cross-group ledger.
7. When fixes are authorized, correct validator failures caused by the change before continuing; otherwise document failures or blockers.
8. Record files changed, or state that the pass was read-only, and record the group outcome.

If prior work was an undifferentiated review, treat it as preliminary context and rerun the applicable grouped passes before claiming orchestrator completion.

## Final Summary

End with:

- each changed file and why
- every selected and skipped group
- focused skill and reference files actually loaded
- table-ready evidence when invoked by `repo-review`
- validators and results
- non-overlapping validation ledger, including why any rerun was necessary
- fixed findings and the mandatory Final Synthesis classification of every remaining risk, or an explicit no-residual-risk result
- anything intentionally deferred
- confirmation that no git state mutations were performed, if true

Lead with unresolved blockers rather than burying them in an all-clear summary.
