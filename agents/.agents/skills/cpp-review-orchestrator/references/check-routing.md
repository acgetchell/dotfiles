# C++ Changed-File Routing

Use this matrix after inspecting scoped files. Prefer repository-documented validators, then the smallest generic validator that covers the risk.

## Scope Detection

Use read-only git commands unless the parent orchestrator already supplied scope:

```bash
git --no-pager status --short
git --no-pager diff --stat
git --no-pager diff --name-status
git --no-pager diff
```

For staged-only requests, add `--cached`. Classify:

- `*.cc`, `*.cpp`, `*.cxx`: C++ implementation
- `*.c`: C source; include only when build metadata proves the file is compiled as C++, otherwise use a C-capable reviewer
- `*.hh`, `*.hpp`, `*.hxx`: C++ headers and public or internal contracts
- `*.h`: language-ambiguous header; include when its owning target or surrounding source establishes C++ semantics
- `*.ixx`, `*.cppm`: modules
- `tests/**`, `test/**`: tests and fixtures
- `bench/**`, `benches/**`, `benchmarks/**`: benchmarks and benchmark fixtures
- `examples/**`: public samples and executable documentation
- `CMakeLists.txt`, `cmake/**`, `CMakePresets.json`, toolchain files, `vcpkg.json`, Conan manifests: build and dependency surfaces
- `.clang-tidy`, `.clang-format`, cppcheck configuration, sanitizer suppressions: static-analysis and diagnostic surfaces
- `justfile`, `.github/workflows/**`: shared project-tooling surfaces

## Skill Group Selection

| Changed surface | Select these groups |
|---|---|
| Resource owners, raw or smart pointers, references, views, iterators, handles, callbacks, coroutines, promises, awaiters, suspension points, container mutation, C interfaces | Lifetime/Ownership, Validation/Test; add Invariant and Final Synthesis when stateful behavior changes |
| Constructors, destructors, factories, move construction or assignment, validation, caches, mutation, topology, rollback, transaction-style updates, inverse operations | Exception/Error Contracts, Invariant/State, Validation/Test, Final Synthesis; add Lifetime/Ownership when handles, borrows, or resources are involved |
| `throw`, `try`, `catch`, `noexcept`, exception guarantees, `std::expected`, `std::error_code`, result/status/optional returns, assertions, termination, partial failure, parsing, serialization, filesystem, networking, callbacks, plugin interfaces, C interoperability, or ABI error translation | Exception/Error Contracts, Validation/Test; add Lifetime/Ownership for cleanup, Invariant/State for post-failure state, Concurrency/Reentrancy for execution boundaries, and Final Synthesis for public contracts |
| Numerical, geometric, combinatorial, stochastic, simulation, or scientific code | Invariant/State, Scientific Correctness, Validation/Test, Final Synthesis; add Lifetime/Ownership when library handles or views are involved |
| Threads, TBB, OpenMP, tasks, locks, atomics, signal handlers, callbacks, shared caches, globals, or shared RNG | Lifetime/Ownership, Invariant/State, Concurrency/Reentrancy, Validation/Test, Final Synthesis; add Exception/Error Contracts for worker, callback, or boundary failures |
| Public headers, signatures, templates, concepts, modules, type contracts, ODR, linkage, inline definitions, explicit instantiation, or ABI | Invariant/State when validity contracts change, Exception/Error Contracts when failure specifications change, Validation/Test, Final Synthesis |
| Allocation, control flow, implementation cleanup, or hot paths | Lifetime/Ownership where relevant, Validation/Test, Final Synthesis; add Scientific Correctness when arithmetic or stochastic behavior can change |
| C++ tests or fixtures only | Validation/Test; add every owning domain group represented by the behavior under test, including Lifetime/Ownership, Invariant/State, Exception/Error Contracts, Scientific Correctness, or Concurrency/Reentrancy |
| Examples or benchmark fixtures | Validation/Test and Final Synthesis; add Scientific Correctness before accepting scientific fixtures or performance claims |
| CMake, dependency manifests, compiler flags, warnings, or sanitizer configuration | Final Synthesis when C++ compilation or diagnostics change; also route to `project-tooling-review` |
| Workflow or recipe only | No C++ group unless C++ coverage, compiler matrix, flags, tests, or sanitizer semantics change; route to `project-tooling-review` |
| Docs-only C++ examples, API contracts, or scientific claims | Relevant C++ group only when executable behavior or correctness claims must be verified; otherwise route to documentation review |

## Focused Validators

Prefer project recipes and presets. If none exist, adapt these fallbacks to the repository rather than inventing unsupported flags.

| Risk or files touched | Focused validation |
|---|---|
| Core implementation | configure/build the affected target, run targeted CTest or test executable, and enforce documented warnings |
| Lifetime, bounds, or undefined behavior | targeted ASan plus UBSan build and tests; add LeakSanitizer or Valgrind when supported and relevant |
| Invariant or topology mutation | deterministic success, rejection, failure-atomicity, and inverse/property tests under ASan/UBSan |
| Exception guarantees or error contracts | focused success/failure tests, injected failures before and after mutation, post-failure state checks, boundary translation tests, and compile-time `noexcept` assertions where contractual |
| Numerical or scientific behavior | known-value, adversarial, metamorphic/property, and independent-oracle tests for affected regimes |
| Stochastic behavior | deterministic seeded replay plus distribution, proposal/acceptance, or reproducibility checks |
| Concurrency | deterministic synchronization tests and ThreadSanitizer on a supported platform; add bounded stress with replay context |
| Tests only | named test case/executable, then the affected CTest label or suite |
| Public headers, templates, or modules | build direct consumers/examples and affected tests; add multi-translation-unit linkage or module-consumer checks for ODR/ABI risk; include supported compiler variants when portability-sensitive |
| Examples | build and run examples whose output or behavior is part of the contract |
| Benchmarks | benchmark compile/smoke validation; measure only when performance claims or optimization are in scope |
| CMake, manifests, or toolchains | configure the affected preset and run project-tooling validators |
| Formatting or static-analysis config | repository `clang-format` dry run, `clang-tidy`, cppcheck, or documented wrapper recipe |

Do not silently broaden sanitizer claims. ASan does not prove race freedom, TSan does not prove lifetime safety, and a job that merely builds with sanitizer flags without executing relevant tests is insufficient.

## Escalation to Full CI

Escalate when repository instructions require it, public contracts and core invariants changed together, multiple C++ layers have coupled risk, mutation/topology/scientific behavior changed broadly, or final synthesis finds risk not covered by focused checks.

Keep focused validation for docs-only, config-only, tests-only, examples-only, or benchmark-only changes when repository guidance permits it.

## Review Summary Template

```text
Changed files:
- path: reason and finding addressed

Review passes:
- Lifetime/Ownership: skills and outcome
- Invariant/State: skills and outcome
- Exception/Error Contracts: skills and outcome
- Scientific Correctness: skills and outcome
- Concurrency/Reentrancy: skills and outcome
- Validation/Test: skills and outcome
- Final Synthesis: remaining risk or none

Validation:
- command: pass/fail/blocked with concise context

Git:
- No git state mutations performed.
```
