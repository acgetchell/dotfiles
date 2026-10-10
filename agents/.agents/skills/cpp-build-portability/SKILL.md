---
name: cpp-build-portability
description: "Audit C++ compilation, linkage, public headers, and supported build configurations when build or portability contracts change."
---

# C++ Build Portability

Verify that every supported build compiles and links the same intended C++ program. Treat translation-unit boundaries, target properties, compiler and standard-library combinations, and configuration variants as correctness surfaces rather than incidental build mechanics.

## Toolchain Defaults

Select this skill from the language and affected contract in any repository.
Use the following defaults when no project policy exists; respect an existing
project toolchain and support policy without requiring a profile or migration.

Use C++23, target-based CMake, checked-in `CMakePresets.json`, vcpkg manifest mode, and `just` as the command surface. Let presets select generators and vcpkg triplets for the supported compiler/platform matrix; do not hardcode one local generator as universal.

Use clang-format and clang-tidy for compiler-aware formatting/static analysis and Semgrep for repository-owned policy rules. Use doctest through CMake/CTest for tests. Route their command wiring and version pins to `project-tooling-review` and semantic test strength to `cpp-test-quality`.

Do not add parallel build systems, dependency managers, test frameworks, command runners, or static-analysis stacks unless the user explicitly requests interoperability. A standards-compliant installed CMake package remains a consumer contract, not a reason to maintain a second project workflow.

## Ground Rules

- Read repository-local guidance before reviewing or editing. Treat its exact recipe and preset names, supported platforms, compilers, libraries, and configurations as the contract unless the user explicitly changes it.
- Check that target compile features and supported presets enforce the declared C++ standard consistently. C++23 is the default for new work; changing an established standard or support matrix requires a project or user goal.
- Do not mutate git state unless the user has explicitly authorized that operation and scope.
- Default to changed files plus the target definitions, public consumers, generated headers, and configuration variants needed to understand their compilation contract.
- Verify current compiler, standard-library, module, and build-system support from authoritative sources when version sensitivity matters. Do not bake a remembered support table into a finding.
- Do not claim portability from one successful compiler, configuration, or CI job. Distinguish declared, configured, compiled, linked, and tested support.
- Do not expand a project's support matrix merely because another toolchain exists. Require an explicit project or user portability goal.

Keep `just` recipe ergonomics, workflow wiring, tool pins, and CI maintenance under `project-tooling-review`. This skill owns the C++ meaning of CMake/vcpkg configuration and whether supported builds agree. Keep intended public API and ABI evolution under `cpp-api-design`, semantic assertion strength under `cpp-test-quality`, and final integration judgment under `cpp-production-review`.

## Audit Workflow

### Establish the compilation contract

Record:

- C++ standard and extension mode
- supported operating systems, architectures, compilers, and standard libraries
- minimum and reference toolchain versions
- CMake configure/build/test presets and inheritance
- vcpkg builtin baseline, manifest features, overrides, registries/overlays, host/target triplets, and binary-cache assumptions
- debug, release, static, shared, sanitizer, coverage, LTO, unity, PCH, and module configurations that are claimed
- exception, RTTI, assertion, visibility, runtime-library, and ABI settings
- public dependencies whose headers, macros, templates, or link interfaces affect consumers

Separate configurations that are documented as supported from experimental or maintainer-only diagnostics. Record which matrix cells are actually available locally or in CI rather than inferring coverage from configuration files.

### Reconstruct targets and translation units

For each affected target, trace:

- source and module units compiled into it
- public, private, generated, and system include paths
- compile features, definitions, options, and language mode
- public and private link dependencies and propagated usage requirements
- vcpkg packages/features and imported targets that supply those dependencies
- generated configuration headers and their owning target
- install/export consumers, examples, tests, plugins, and bindings that compile the public surface

Prefer target-scoped properties over accidental directory-global state. Compare the effective properties of a library with every consumer that must agree with it. Use build-system introspection or `compile_commands.json` when available, but verify generated commands belong to the intended configuration.

### Require self-contained headers

Check that each public header:

- compiles as the first include in a minimal translation unit
- directly includes the declarations it uses instead of relying on include order, a PCH, unity aggregation, or transitive dependency headers
- has reliable multiple-inclusion protection
- does not leak macros, `using` directives, or configuration accidents into consumers
- uses forward declarations only where completeness, ownership, deletion, and ABI rules permit them
- presents the same declarations to all consumers that share an ABI or ODR boundary

Check representative private headers when include order, unity builds, or generated definitions make them similarly fragile. Treat a PCH or unity build that conceals missing includes as a defect in the underlying source contract.

### Audit ODR and linkage

Check:

- non-template definitions in headers have correct `inline` or internal-linkage semantics
- inline functions and variables, variable templates, `constexpr` static data, and defaulted members have one equivalent definition
- macros and configuration headers cannot produce different class layouts, exception specifications, constraints, or inline bodies across translation units
- templates needed by consumers are defined where instantiated or backed by complete explicit-instantiation declarations and definitions
- anonymous namespaces and internal-linkage entities in headers do not create unintended per-translation-unit type or state identity
- symbol visibility, export/import annotations, calling conventions, and `extern "C"` boundaries match static and shared-library contracts
- public inheritance, virtual interfaces, key functions, type information, and runtime-library settings do not create missing or incompatible symbols

Do not dismiss an ODR risk because the linker accepts it; many violations are ill-formed with no diagnostic required or surface only under LTO, optimization, dynamic linking, or a downstream consumer.

### Audit compiler and library portability

Distinguish language support from standard-library availability. Check:

- C++23 facilities exist in each supported compiler and selected standard library
- standard feature-test macros or build-time capability checks guard optional facilities precisely
- compiler-brand or version checks do not stand in for the actual capability
- vendor extensions, permissive modes, warning differences, and nonstandard predefined macros are intentional
- integer widths, signedness, endianness, alignment, path behavior, and platform types are not assumed beyond the supported contract
- dependency APIs and required compile definitions match the versions and platforms being built

Treat multiple compilers as independent correctness evidence: different front ends and libraries expose different diagnostics and assumptions. Do not weaken warnings or behavior merely to make the matrix superficially green.

### Configuration and modules

When configuration variants or modules affect the change, read
[configuration and module boundaries](references/configuration-and-modules.md).

### Validate the matrix proportionally

Use repository `just` recipes first; require them to delegate to the declared CMake presets and vcpkg manifest. If a needed recipe is absent, use the checked-in preset directly and report the missing command-surface coverage rather than inventing another workflow. Select the smallest evidence that proves the affected contract:

1. compile minimal consumers with each changed public header first
2. compile and link a two-or-more-translation-unit consumer for ODR, visibility, and explicit-instantiation risks
3. configure and build affected debug and release targets
4. exercise static and shared consumers when both are supported
5. build and run focused tests with each relevant compiler and standard-library pairing available
6. build installed/exported-package consumers when downstream use is claimed
7. exercise module, PCH, unity, LTO, sanitizer, exception, RTTI, or runtime-library variants only when affected or supported
8. escalate to the documented full compiler/platform matrix when a public contract, common header, target usage requirement, or configuration boundary changes broadly

Record compiler, standard-library, CMake, generator, vcpkg baseline/triplet, dependency, and configuration versions with each result. Mark unavailable matrix cells as unverified; do not convert configuration presence into demonstrated support.

## Finding Standard

For each finding, name the affected compiler, library, platform, target, translation units, or configuration; show the compile, link, ODR, ABI, or behavioral failure; identify the violated support contract; and give the smallest portable correction plus focused validation. Distinguish a confirmed supported-matrix defect from an unverified portability hypothesis or optional matrix expansion.

## Handoff

Summarize the declared and demonstrated matrix, CMake presets and vcpkg contract, headers and targets inspected, ODR/linkage and configuration checks, compiler/library evidence, `just` validators and results, unavailable matrix cells, joint work routed to project tooling or API/test specialists, files changed, and confirmation that no git state mutations were performed when true.
