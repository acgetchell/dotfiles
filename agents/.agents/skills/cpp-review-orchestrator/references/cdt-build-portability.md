# CDT++ Build Portability

Load this reference when CDT++ review selects Build and Portability Contract.

## Matrix Contract

- Reconstruct the current compiler, standard-library, operating-system, architecture, dependency, and configuration matrix from repository documentation, presets, workflows, and package metadata. Do not preserve stale matrix assumptions.
- Distinguish front-end coverage from standard-library and platform coverage. Similar compiler families can still exercise different libraries, dependency builds, linkers, or operating systems.
- Treat a failure unique to one supported compiler as a correctness signal until the language, library, dependency, or toolchain contract proves otherwise. Minimize the difference before adding vendor branches or suppressions.
- When a supported matrix cell cannot run locally, name its CI job as pending evidence rather than inferring success from another cell.

## CMake And vcpkg Contract

- Require C++23 through target compile features and every supported configure preset.
- Treat `CMakePresets.json` as the shared configure/build/test matrix and keep machine-local paths or credentials out of tracked presets.
- Treat `vcpkg.json`, its builtin baseline/overrides/features, `vcpkg-configuration.json`, overlay ports, and triplets as the dependency contract.
- Keep vcpkg integration selected by the presets/toolchain before CMake's first `project()` call; do not mix manifest and ambient classic-mode dependencies.
- Test the vcpkg features/triplets affected by a dependency or linkage change and preserve host-versus-target distinctions for cross builds.

## Target and Consumer Contract

- Require public headers and template-heavy CGAL-facing code to compile without accidental include order, PCH, unity-build, or transitive-header support.
- Exercise multi-translation-unit consumers when inline definitions, explicit instantiations, configuration macros, or CGAL type aliases change.
- Keep C++ standard, assertions, exceptions, RTTI, visibility, dependency features, and generated configuration consistent across libraries, tests, examples, and downstream consumers wherever ODR or ABI agreement is required.
- Keep test executables on the same relevant target usage requirements and production dependencies as the behavior they exercise.

## Focused Validation

- Confirm named `just` recipes and presets exist before invoking them.
- Start with the repository's documented reference configure, build, and smoke-test contract.
- Escalate portability-sensitive headers, templates, macros, linkage, or dependency-boundary changes to the affected supported matrix cells.
- Route CMake/vcpkg command ergonomics, `just` recipes, workflow wiring, Semgrep/Clang configuration mechanics, and tool pins jointly to `project-tooling-review`.
