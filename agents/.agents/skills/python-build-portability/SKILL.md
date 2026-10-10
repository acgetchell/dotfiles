---
name: python-build-portability
description: "Audit Python package builds, installed consumers, and supported runtime or platform configurations."
---

# Python Build Portability

Audit the boundary between a Python checkout and the environments that consume it. Prove that declared support matches built and installed behavior rather than assuming success from an in-tree test run.

## Toolchain Defaults

Select this skill from the language and affected contract in any repository.
Use the following defaults when no project policy exists; respect an existing
project toolchain and support policy without requiring a profile or migration.

Use the repository's validation recipes and established tools. When no project policy exists, use these defaults:

- uv owns Python acquisition, project environments, dependency resolution and locking, command execution, builds, and isolated installation.
- Ruff owns linting, import sorting, and formatting.
- ty owns static type checking.
- `pyproject.toml` owns project metadata and tool configuration; `uv.lock` records the reproducible development resolution.

Do not add a parallel project/environment, lint/format, or type-check workflow merely to perform this review. Preserve an established alternative stack unless a migration is requested. A published wheel remaining standards-compliant is a distribution requirement, not a reason to maintain another project workflow.

Use the established build frontend while auditing the configured `[build-system]` backend: the backend determines artifact contents, metadata, and filenames. Route command wiring, installer recipes, and tool-version drift to `project-tooling-review`.

## Scope

Inspect packaging, imports, configuration, native boundaries, and directly
related tests in the supplied scope. When invoked directly without an exact
parent scope, validation ledger, and result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md).
Review-graph and Python-orchestrator dispatches already own that information.

Derive supported Python versions, operating systems, architectures, and dependency modes from `pyproject.toml`, documentation, workflows, and release policy. Do not invent support the project does not claim.

Read unchanged workflows that execute changed scripts/tests, including projects
with `package = false`. When Windows is supported, read
[Windows boundaries](references/windows-boundaries.md) even without packaging
changes or explicit platform branches.

## Ownership Boundaries

- Own artifact construction, installation, importability, declared compatibility, extras, entry points, and platform-sensitive source behavior here.
- Let `project-tooling-review` own recipe/workflow mechanics and tool pins.
- Let `python-production-review` own ordinary runtime semantics and final integration synthesis.
- Let `python-test-quality` own durable install, consumer, and matrix evidence.
- Let `python-support-scripts` own repository scripts wrapping uv or artifact processing.
- Let documentation reviewers own downstream documentation after technical truth is established.

## Audit Workflow

1. Identify the declared Python, operating-system, architecture, dependency, and artifact matrix.
2. Check the repository lockfile with its established tool (`uv lock --check` for uv); do not silently refresh it during an audit.
3. Ensure environment, lint, and type-check target settings agree with `requires-python` and the supported source surface.
4. Map changed files to build, install, import, entry-point, optional-feature, platform, or native-extension risks.
5. Select the smallest relevant lint and type checks through repository recipes, respecting parent-owned validation commands.
6. Produce the wheel and sdist with the established build frontend when artifact semantics changed (`uv build` for uv projects).
7. Inspect artifacts, install the wheel into an isolated environment outside the checkout using the established environment tooling, and exercise the affected public consumer.
8. Report proven configurations separately from declared but untested support.

Lint and type checks are source/configuration evidence; neither substitutes for building and installing the distribution.

## Project And Locking Semantics

For uv projects, check the following; apply equivalent checks to the established toolchain in other projects:

- `[project]`, dependency groups, optional dependencies, scripts, entry points, and `[tool.uv]` express distinct runtime, development, and source-resolution concerns
- `uv.lock` is current, committed when repository policy requires it, and resolves the declared marker space
- locked development packages are not mistaken for published runtime dependencies
- `uv run --locked` or equivalent recipes fail on stale metadata instead of rewriting the lock during CI validation
- exact/minimal syncs do not rely on undeclared ambient packages
- workspaces, local sources, and editable members do not leak into release artifacts unintentionally
- platform, architecture, implementation, and Python-version markers agree with reachable code paths

Do not use a successful rich development sync as evidence that minimal or optional installations work.

## Packaging

When distribution contents, build hooks, resources, or installation change, read
[packaging and installation](references/packaging.md).

## Ruff And ty Alignment

When the project uses Ruff, check that its target version, selected rules, exclusions, import policy, and formatter configuration match the supported Python surface. Run lint before format checking when import sorting or fixable lint rules are part of the repository contract.

When the project uses ty, check that it discovers the installed packages and source roots intended by the project, targets a compatible Python version, includes public modules, and does not pass only because the checkout exposes undeclared import paths or development dependencies.

Treat tool suppressions and per-file exclusions as configuration-sensitive behavior. Route policy quality to production or tooling review when it is not specifically a portability issue.

## Runtime, Platform, And Consumer Matrix

Review syntax, standard-library APIs, typing syntax, and deprecations against the declared minimum Python version. Check claimed CPython, PyPy, free-threaded, operating-system, architecture, path, case-sensitivity, permission, encoding, locale, timezone, binary-format, and native-library behavior only where the repository declares or exercises it.

Check console/plugin entry points, public imports, optional-feature failures, metadata lookup, and package resources after wheel installation. Validate a minimal external consumer when the public import surface or installation contract changes.

For native components, check wheel tags, ABI/runtime requirements, shared-library discovery, build isolation, representation boundaries, and explicit unsupported-platform failures. Route native algorithm correctness to the owning language specialist.

Exercise only the configurations needed to distinguish the risk. Use the established interpreter/environment selection rather than adding a second matrix runner, and record unavailable runtimes or platforms as evidence gaps.
