# CDT++ Routing Notes

Use this reference when `cpp-review-orchestrator` is running in CDT++ or closely related C++ causal-dynamical-triangulation and CGAL code.

## Repository Sources of Truth

- Read local instructions first, then the current testing and sanitizer sections of `README.md`, `.github/CONTRIBUTING.md`, `justfile`, `CMakePresets.json`, `tests/CMakeLists.txt`, and the relevant CMake modules or workflows.
- Prefer repository `just` recipes and presets over generic CMake fallbacks. Treat those files as authoritative when this reference and the repository diverge.
- Keep review guidance here; keep contributor-facing commands and policy in repository-owned documentation so they remain visible outside Codex.

## Review Emphasis

- Preserve the supported C++23 contract and verify behavior across the repository's supported compilers and platforms when portability-sensitive code changes.
- Treat CGAL handles, iterators, circulators, and references as invalidation-sensitive across insertion, removal, flips, swaps, copies, moves, and triangulation replacement. Verify guarantees from the installed CGAL version or current official documentation rather than assuming stability.
- For 2-to-3, 3-to-2, 4-to-4, 2-to-6, and 6-to-2 moves, verify preconditions, exact simplex-count deltas, causal foliation, reciprocal adjacency, orientation, manifold validity, and failure atomicity. A rejected move must not partially mutate the manifold.
- Prefer CGAL public primitives when they express the required operation, but do not replace working topology code solely for API novelty. Preserve scientific behavior and deterministic regression oracles.
- When randomness is in scope, keep RNG ownership explicit at the simulation, test, or benchmark level; pass it by reference, retain deterministic replay, and keep distributions separate from the engine. Check proposal and acceptance probabilities independently.
- Do not require parse-don't-validate or a broad API rewrite. Recommend architectural work only when it is the smallest credible fix for a verified defect; otherwise record it as a separate follow-up.

## doctest and BDD Policy

- Treat doctest as the canonical CDT++ C++ test framework. Do not recommend Catch2 or GoogleTest without a concrete missing capability that matters to this repository.
- Prefer `SCENARIO`, `GIVEN`, `WHEN`, and `THEN` for domain behavior, scientific invariants, and state transitions. Use ordinary doctest cases or templates when BDD would add ceremony to table-driven algorithms, compile-time properties, or narrow regressions.
- Remember that BDD clauses map to doctest subcases and can rerun enclosing setup. Avoid many microscopic `THEN` branches after expensive CGAL construction; group related independent postconditions when one outcome is being specified.
- Use fatal assertions for prerequisites that make later checks unsafe or meaningless. Use nonfatal checks for independent postconditions so one failure does not hide the rest of the state.
- Keep ordinary new unit tests under `tests/`, name them consistently with the repository convention, and register new source files in `tests/CMakeLists.txt`. Treat existing source-embedded scenarios as special cases rather than a default location for new tests.
- Require independent assertions: exact counts, incidence and orientation properties, canonical snapshots, inverse operations, known scientific values, or deterministic seeds. Do not rely only on production validity helpers as the oracle.

## CMake and CTest Contract

- Preserve the supported reference build and its deliberately selective `reference-smoke` preset. Read the current exclusions before treating a full CTest failure as a regression or broadening the smoke gate.
- Keep test executables linked to the same project options, warnings, C++ standard, and relevant production dependencies as the behavior they exercise.
- Register every intended test path with CTest and use `--no-tests=error` or the preset's equivalent in CI and diagnostic jobs so missing discovery fails visibly.
- Consider `doctest_discover_tests()` only when per-scenario reporting materially helps. Before adopting it, preserve suite filters, timeouts, working directories, expensive or nondeterministic exclusions, and cross-compilation behavior; do not double-register scenarios alongside overlapping `add_test()` entries.
- Keep CMake/CTest and workflow wiring under joint ownership with `project-tooling-review`. This C++ pass owns whether the registered tests provide meaningful behavioral evidence.

## Sanitizer and Diagnostic Contract

- Treat ASan plus UBSan as the primary memory and undefined-behavior pairing. Keep standalone LSan and TSan separate where required by the compiler runtime.
- Treat MSan as experimental unless the standard library and dependencies are instrumented; do not present a clean or noisy partial-instrumentation run as authoritative.
- Verify sanitizer jobs execute the relevant doctest/CTest cases and representative long-running binaries. Compiling with sanitizer flags alone is not coverage.
- Preserve nonzero error propagation, symbolized diagnostics, frame pointers, and test output on failure. Do not add suppressions before verifying the report and minimizing a reproducer.
- Account for platform support. A clean ASan run does not establish race freedom, and a clean TSan run does not establish lifetime or bounds safety.

## Focused Validation

- Before invoking the named validators, inspect the target repository's `justfile`, `CMakePresets.json`, and validation documentation to confirm that `just check`, `just build`, `just ci`, and the `reference-smoke` preset exist. Supported CDT++ repositories should use the documented commands they define. Closely related repositories without those targets must use their documented validation fallback; a missing recipe or preset is not itself a validation failure.
- When defined, use `just check` for fast non-mutating source and configuration validation; it does not replace a C++ build.
- When defined, use `just build` for the supported reference configure, build, and smoke-test contract.
- When defined, use `just ci` for the comprehensive local gate when changes cross code, test, and tooling surfaces or before a release-ready handoff.
- After a reference build, run the affected doctest suite or executable directly while iterating. Rerun `ctest --preset reference-smoke` only when that preset exists; otherwise use the repository's documented test fallback. Run the full registered CTest set only when its current documented known-failure and nondeterminism status is understood.
- Use the repository sanitizer, static-analysis, and coverage scripts or workflows for their corresponding risks. Inspect them before execution because diagnostic scripts may recreate the local `build/` directory and may exercise more than unit tests.
