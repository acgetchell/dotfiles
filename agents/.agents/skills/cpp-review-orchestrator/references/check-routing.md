# C++ Review Routing

Use this matrix after inspecting scoped files. Prefer repository `just` recipes backed by CMake presets, vcpkg manifest mode, doctest/CTest, Semgrep, clang-format, and clang-tidy. If the command surface lacks required coverage, use the configured tool directly and report the gap; do not introduce an alternate stack.

## Scope Detection

Use read-only git commands unless the parent orchestrator already supplied scope:

```bash
git --no-pager status --short
git --no-pager diff --stat
git --no-pager diff --name-status
git --no-pager diff
git ls-files --others --exclude-standard
```

The diff commands cover tracked paths only. Inspect the contents of every path returned by `git ls-files --others --exclude-standard` with a file-appropriate reader, and include each untracked file in scope classification and review evidence. Do not treat its status entry or filename alone as inspection.

For staged-only requests, add `--cached` to the diff commands. Classify:

- `*.cc`, `*.cpp`, `*.cxx`: C++ implementation
- `*.c`: C source; include only when build metadata proves the file is compiled as C++, otherwise use a C-capable reviewer
- `*.hh`, `*.hpp`, `*.hxx`: C++ headers and public or internal contracts
- `*.h`: language-ambiguous header; include when its owning target or surrounding source establishes C++ semantics
- `*.ixx`, `*.cppm`: modules
- `tests/**`, `test/**`: tests and fixtures
- `bench/**`, `benches/**`, `benchmarks/**`: benchmarks and benchmark fixtures
- `examples/**`: public samples and executable documentation
- `Doxyfile*`, `doxygen/**`, documentation-generator configuration, generated API-site sources: C++ API documentation surfaces
- `CMakeLists.txt`, `cmake/**`, `CMakePresets.json`, toolchain files, `vcpkg.json`, `vcpkg-configuration.json`, overlay ports, and triplets: build and dependency surfaces
- `.clang-tidy`, `.clang-format`, Semgrep configuration/fixtures, and sanitizer suppressions: static-analysis and diagnostic surfaces
- `justfile`, `.github/workflows/**`: shared project-tooling surfaces

## Skill Group Selection

Use this table to select optional specialist groups 1–11. Always run Final Synthesis after the selected specialists, so it is not conditional on a table entry.

| Changed surface | Select these groups |
|---|---|
| Resource owners, raw or smart pointers, references, views, iterators, handles, callbacks, coroutines, promises, awaiters, suspension points, container mutation, C interfaces | Lifetime/Ownership, Validation/Test; add Invariant when stateful behavior changes and API Design when a public signature expresses ownership or borrowing |
| Constructors, destructors, factories, move construction or assignment, validation, caches, mutation, topology, rollback, transaction-style updates, inverse operations | Exception/Error Contracts, Invariant/State, Validation/Test; add Parse/Invalid-State when raw input or discarded validation evidence is involved, Lifetime/Ownership when handles, borrows, or resources are involved, and API Design when public construction or conversion changes |
| Raw DTOs or primitives entering domain logic, parsers, deserialization, configuration, builders, strong value types, enum-like values, public invariant-bearing aggregates, checked numeric conversion, repeated validation, or setters that can store invalid values | Parse/Invalid-State, Invariant/State, Exception/Error Contracts, Validation/Test; add Lifetime/Ownership for borrowed input or exposed aliases and API Design when the boundary is public or cross-module |
| `throw`, `try`, `catch`, `noexcept`, exception guarantees, `std::expected`, `std::error_code`, result/status/optional returns, assertions, termination, partial failure, parsing, serialization, filesystem, networking, callbacks, plugin interfaces, C interoperability, or ABI error translation | Exception/Error Contracts, Validation/Test; add Parse/Invalid-State when the boundary establishes a domain invariant, Lifetime/Ownership for cleanup, Invariant/State for post-failure state, API Design when a public failure channel or signature changes, and Concurrency/Reentrancy for execution boundaries |
| Numerical, geometric, combinatorial, stochastic, simulation, or scientific code | Invariant/State, Scientific Correctness, Validation/Test; add Lifetime/Ownership when library handles or views are involved |
| Threads, TBB, OpenMP, tasks, locks, atomics, signal handlers, callbacks, shared caches, globals, or shared RNG | Lifetime/Ownership, Invariant/State, Concurrency/Reentrancy, Validation/Test; add Exception/Error Contracts for worker, callback, or boundary failures and API Design when thread-safety or callback contracts are public |
| Public headers, signatures, templates, concepts, modules, type contracts, ODR, linkage, inline definitions, explicit instantiation, or ABI | Build/Portability, API Design, API Documentation, Validation/Test; add Invariant/State when validity contracts change, Exception/Error Contracts when failure specifications change, and Lifetime/Ownership when borrowing or invalidation is exposed |
| Compiler- or platform-specific code, feature-test or configuration macros, generated configuration headers, export annotations, static/shared boundaries, PCH, unity builds, LTO, exception/RTTI/assertion modes, or supported compiler/library failures | Build/Portability, Validation/Test; add API Design when public declarations or ABI exposure change and route command or workflow mechanics jointly to `project-tooling-review` |
| Standard algorithms, ranges, lazy views, transformation pipelines, folds, higher-order functions, non-trivial lambda capture, `optional`/`expected`/`variant` composition, or substantial loop/pipeline refactors | Functional Style, Validation/Test; add API Design when the transformation or generic contract is public, Lifetime/Ownership for borrowed views or captures, Exception/Error Contracts for fallible stages, Scientific Correctness for arithmetic reordering, and Concurrency/Reentrancy for parallel execution |
| Allocation, control flow, implementation cleanup, or hot paths | Functional Style when data-flow design is material, Lifetime/Ownership where relevant, Validation/Test; add Scientific Correctness when arithmetic or stochastic behavior can change |
| C++ tests or fixtures only | Validation/Test; add every owning domain group represented by the behavior under test, including Build/Portability for compile/link consumers or matrix behavior, Lifetime/Ownership, Invariant/State, Parse/Invalid-State, Exception/Error Contracts, API Design, Functional Style, Scientific Correctness, or Concurrency/Reentrancy |
| Examples or benchmark fixtures | Validation/Test; add API Design and API Documentation when examples define canonical public usage, and Scientific Correctness before accepting scientific fixtures or performance claims |
| CMake, dependency manifests, compiler flags, warnings, sanitizer configuration, module graph, target usage requirements, or generated configuration | Build/Portability when C++ language, ODR, linkage, ABI, dependency, or configuration semantics change; always route command and configuration mechanics jointly to `project-tooling-review` |
| Workflow or recipe only | Build/Portability only when supported compiler/library coverage or configuration semantics change; otherwise route to `project-tooling-review` |
| Doxygen configuration, C++ public comments, generated reference sources, or API guides | API Documentation; add API Design and the relevant ownership/error/concurrency/scientific group when claimed behavior must be established, Build/Portability for supported consumption/platform claims, Validation/Test for executable examples, and `project-tooling-review` for generator command wiring |
| Docs-only C++ examples, API contracts, portability claims, or scientific claims | API Documentation; add API Design for public contract or canonical-usage truth, Build/Portability for compiler/platform support claims, and the relevant scientific group for correctness claims; route suite-level placement and cross-document consistency to documentation review |

## Focused Validators

Prefer project recipes and presets. Inspect their expanded test selections before execution and maintain a ledger keyed by source/build/configuration and test IDs. Never rerun still-valid test evidence; a different compiler, standard library, sanitizer, linkage mode, or material configuration is a distinct matrix cell. If no recipe exists, use the configured tool directly and report the command-surface gap.

| Risk or files touched | Focused validation |
|---|---|
| Core implementation | configure/build the affected target, run targeted CTest or test executable, and enforce documented warnings |
| Lifetime, bounds, or undefined behavior | targeted ASan plus UBSan build and doctest/CTest execution; add standalone LeakSanitizer when supported and relevant |
| Invariant or topology mutation | deterministic success, rejection, failure-atomicity, and inverse/property tests under ASan/UBSan |
| Boundary parsing or invalid-state prevention | focused acceptance/rejection and round-trip tests, compile-time construction/overload checks, failed-mutation state checks, and sanitizers when aliases or views carry the evidence |
| Exception guarantees or error contracts | focused success/failure tests, injected failures before and after mutation, post-failure state checks, boundary translation tests, and compile-time `noexcept` assertions where contractual |
| Functional transformations or range pipelines | focused equivalence, ordering, duplicate, empty/singleton, short-circuit, and allocation-sensitive tests; add ASan/UBSan for lazy borrowed views and measurements for claimed hot-path improvements |
| ODR, linkage, or configuration agreement | minimal first-include consumers, multi-translation-unit compile/link tests, and affected static/shared, debug/release, macro, LTO, unity, PCH, exception, or RTTI variants |
| Compiler or standard-library portability | affected targets and focused tests under each relevant supported pairing available; record exact versions and mark unavailable matrix cells unverified |
| Numerical or scientific behavior | known-value, adversarial, metamorphic/property, and independent-oracle tests for affected regimes |
| Stochastic behavior | deterministic seeded replay plus distribution, proposal/acceptance, or reproducibility checks |
| Concurrency | deterministic synchronization tests and ThreadSanitizer on a supported platform; add bounded stress with replay context |
| Tests only | choose one smallest sufficient doctest scenario/case, test executable, or CTest selection; use CTest listing to verify registration without executing overlapping tests |
| Public headers, templates, concepts, overloads, or modules | build minimal direct consumers and affected tests; add stable compile-fail constraint cases, multi-translation-unit linkage, or module-consumer checks for overload/ODR/ABI risk; include supported compiler variants when portability-sensitive |
| Examples | build and run examples whose output or behavior is part of the contract |
| Doxygen or generated C++ API docs | run the repository documentation generator with warning policy, validate links/navigation and downstream XML consumers, and compile canonical examples in scope |
| Benchmarks | benchmark compile/smoke validation; measure only when performance claims or optimization are in scope |
| CMake, vcpkg manifest, presets, or toolchains | run the affected `just` recipe and CMake configure/build/test presets across relevant vcpkg triplets/features |
| Formatting or static-analysis config | repository `just` recipes for clang-format dry-run, clang-tidy with the preset's compilation database, Semgrep fixture tests, and the real Semgrep scan |

Do not silently broaden sanitizer claims. ASan does not prove race freedom, TSan does not prove lifetime safety, and a job that merely builds with sanitizer flags without executing relevant tests is insufficient.

## Escalation to Full CI

Escalate when repository instructions require it, public contracts and core invariants changed together, multiple C++ layers have coupled risk, mutation/topology/scientific behavior changed broadly, or final synthesis finds risk not covered by focused checks.

Keep focused validation for docs-only, config-only, tests-only, examples-only, or benchmark-only changes when repository guidance permits it.

Decide whether repository policy or known cross-layer scope requires the full
gate before executing the first test, and inspect the gate's composition then.
If it would rerun tests already passing for the current
source/build/configuration state, run only its uncovered validators or choose
the full gate as the single selection instead of preceding it with overlapping
focused tiers. If a mandatory indivisible gate is discovered late and offers
no reliable exclusion, report the command-surface blocker and route it to
`project-tooling-review`; do not silently replay tests or count them twice. A
relevant edit invalidates prior evidence; mere desire for a broader summary
does not.

## Review Summary Template

```text
Changed files:
- path: reason and finding addressed

Selection:
- Selected group: reason
- Skipped group: reason

Loaded guidance:
- skill/reference path: group and purpose

Review passes:
- Build/Portability: skills and outcome
- Lifetime/Ownership: skills and outcome
- Invariant/State: skills and outcome
- Parse/Invalid-State: skills and outcome
- Exception/Error Contracts: skills and outcome
- API Design: skills and outcome
- API Documentation: skills and outcome
- Functional Style: skills and outcome
- Scientific Correctness: skills and outcome
- Concurrency/Reentrancy: skills and outcome
- Validation/Test: skills and outcome

Findings:
- Fixed: finding and affected files
- Deferred/blocked: finding, reason, and owner

Validation ledger:
- source/build/configuration and exact selection: command, pass/fail/blocked/reused, and rerun rationale when applicable

Final Synthesis:
- residual-risk classification and release-readiness verdict, or explicit no-residual-risk result

Git:
- No git state mutations performed.
```
