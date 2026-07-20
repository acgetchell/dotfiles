# CDT++ Routing Notes

Use this compact reference for every CDT++ or closely related C++ causal-dynamical-triangulation review. Load only the additional CDT++ references selected directly by `cpp-review-orchestrator` for the affected groups.

## Sources of Truth

- Read local instructions first, then the relevant portions of `README.md`, `.github/CONTRIBUTING.md`, `justfile`, `CMakePresets.json`, `tests/CMakeLists.txt`, CMake modules, and workflows.
- Apply the fixed toolchain declared by `cpp-review-orchestrator`. Prefer repository `just` recipes backed by named presets; if required coverage is absent, use the configured tool directly and report the command-surface gap.
- Keep contributor-facing commands and policy in repository documentation; keep agent routing here.

## Cross-Group Policy

- Preserve CDT++'s declared C++23 contract. Treat its compiler and platform matrix as both a portability promise and independent correctness evidence.
- Do not require parse-don't-validate or a broad API rewrite. Recommend architecture only when it is the smallest credible fix for a verified defect; otherwise record a separate follow-up.
- Prefer CGAL public primitives when they preserve the required behavior, but do not rewrite working topology code for API novelty.
- Preserve scientific behavior, deterministic regression oracles, nonzero diagnostic propagation, and user-owned work.
