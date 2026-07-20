# CDT++ Tests and Diagnostics

Load this reference when CDT++ review selects Validation and Test Quality or changes test registration, sanitizer coverage, or diagnostic behavior.

## doctest and BDD

- If doctest lacks a concrete required capability, report it and request an explicit toolchain decision rather than adding another framework.
- Prefer `SCENARIO`, `GIVEN`, `WHEN`, and `THEN` for domain behavior, scientific invariants, and state transitions. Use ordinary cases or templates when BDD adds ceremony to table-driven algorithms, compile-time properties, or narrow regressions.
- Account for doctest subcase re-entry. Avoid many microscopic branches after expensive CGAL setup; group independent postconditions for one outcome.
- Use fatal assertions for prerequisites that make later checks unsafe or meaningless and nonfatal checks for independent postconditions.
- Put ordinary new tests under `tests/`, follow repository naming, and register new sources in `tests/CMakeLists.txt`.
- Require independent oracles such as exact counts, incidence and orientation properties, snapshots, inverse operations, known scientific values, or deterministic seeds.

## CMake and CTest

- Preserve the documented reference build and deliberately selective smoke preset; inspect exclusions before treating a full CTest failure as a regression or broadening the gate.
- Register every intended path and configure CI or diagnostic runs so missing test discovery fails visibly.
- Consider `doctest_discover_tests()` only when per-scenario reporting materially helps, and preserve filters, timeouts, working directories, expensive-test exclusions, nondeterminism policy, and cross-compilation behavior.
- Never double-register scenarios beside overlapping `add_test()` entries, even under a different name or label. A new CTest entry must own a disjoint suite or deliberately replace the prior registration; use doctest filters directly for focused local reruns.
- Route CMake/CTest wiring jointly to `project-tooling-review`; this pass owns whether registered tests provide meaningful evidence.

## Sanitizers and Validation

- Treat ASan plus UBSan as the primary memory and undefined-behavior pairing. Keep standalone LSan and TSan separate where runtime support requires it.
- Treat MSan as experimental unless the standard library and dependencies are instrumented.
- Verify diagnostic jobs execute relevant doctest/CTest cases and representative long-running binaries; compilation with sanitizer flags is not coverage.
- Preserve nonzero exits, symbolized diagnostics, frame pointers, and failure output. Minimize reports before adding suppressions.
- A clean ASan run does not establish race freedom; a clean TSan run does not establish lifetime or bounds safety.
- Record the source/build/configuration and exact test IDs covered by every command. Never run a case, its containing suite, its monolithic CTest registration, and full CI as nested successive tiers when earlier evidence remains valid.
- Confirm recipes and presets exist before invoking them. Inspect recipe expansion and choose one smallest sufficient test selection. Use CTest listing to check registration without execution. Use a preset directly only when no recipe covers the required build, and report that command-surface gap.
- Treat the same scenario under ASan/UBSan, TSan, another supported compiler/library pair, or another material configuration as distinct evidence. Rerun an ordinary test only after a relevant edit invalidates it or when diagnosing nondeterminism.
- Inspect sanitizer, analysis, and coverage scripts before execution because they may recreate `build/` or exercise more than unit tests.
