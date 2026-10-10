# C++ Configuration and Module Boundaries

## Audit configuration-sensitive behavior

Compare declarations and behavior across relevant configurations, including:

- `NDEBUG` and assertion settings
- exceptions and RTTI enabled or disabled
- standard-library iterator or debug modes
- sanitizer and coverage instrumentation
- static versus shared linkage and symbol visibility
- debug versus optimized builds, LTO, unity builds, and PCH use
- platform and dependency feature macros
- floating-point, architecture, and runtime-library options when they affect semantics or ABI

Require every ODR- or ABI-sensitive definition to see compatible settings. Validation reachable from ordinary inputs must not disappear only because release builds disable assertions.

## Audit modules

When modules are supported, check:

- interface units, implementation units, and partitions form an explicit dependency graph
- exported declarations have reachable dependencies and do not rely on accidental textual inclusion
- global module fragments contain only required legacy-header or macro setup
- macros are not expected to cross an `import` boundary
- headers are not inconsistently imported and textually included in ways that duplicate or change declarations
- module ownership, visibility, and explicit instantiation agree with non-module consumers where both are supported
- binary module interfaces are treated as compiler-, version-, flag-, and configuration-specific artifacts

Do not claim module portability from one experimental toolchain. Verify the exact supported compiler, standard library, generator, and build-system combination.
