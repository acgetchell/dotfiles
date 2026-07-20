---
name: python-build-portability
description: "Audit uv-managed Python packaging, locking, building, installation, imports, runtime and platform support, optional dependencies, entry points, native extensions, and configuration-sensitive behavior. Use for pyproject.toml, uv.lock, uv build/sync/run behavior, wheels, sdists, package discovery/data, extras, markers, supported Python or OS matrices, editable-versus-built differences, and external consumers. Use Ruff for lint and format validation and ty for type validation; do not introduce alternate Python project, lint, format, or type-check toolchains."
---

# Python Build Portability

Audit the boundary between a Python checkout and the environments that consume it. Prove that declared support matches uv-built and uv-installed behavior rather than assuming success from an in-tree test run.

## Fixed Toolchain Contract

Use the repository's `just` recipes when present and require their Python commands to resolve through the following toolchain:

- uv owns Python acquisition, project environments, dependency resolution and locking, command execution, builds, and isolated installation.
- Ruff owns linting, import sorting, and formatting.
- ty owns static type checking.
- `pyproject.toml` owns project metadata and tool configuration; `uv.lock` records the reproducible development resolution.

Do not add or preserve parallel project/environment, lint/format, or type-check workflows unless the user explicitly requests interoperability with another tool. A published wheel remaining standards-compliant is a distribution requirement, not a reason to maintain another project workflow.

Use uv as the build frontend while auditing the configured `[build-system]` backend: the backend still determines artifact contents, metadata, and filenames. Route command wiring, installer recipes, and uv/Ruff/ty version drift to `project-tooling-review`.

## Scope

Use changed-code mode by default. Inspect changed packaging, imports, configuration, native boundaries, and directly related tests. Use whole-repository mode only for an explicit baseline or release-readiness audit.

Derive supported Python versions, operating systems, architectures, and dependency modes from `pyproject.toml`, documentation, workflows, and release policy. Do not invent support the project does not claim.

## Ownership Boundaries

- Own artifact construction, installation, importability, declared compatibility, extras, entry points, and platform-sensitive source behavior here.
- Let `project-tooling-review` own recipe/workflow mechanics and tool pins.
- Let `python-production-review` own ordinary runtime semantics and final integration synthesis.
- Let `python-test-quality` own durable install, consumer, and matrix evidence.
- Let `python-support-scripts` own repository scripts wrapping uv or artifact processing.
- Let documentation reviewers own downstream documentation after technical truth is established.

## Audit Workflow

1. Identify the declared Python, operating-system, architecture, dependency, and artifact matrix.
2. Check `uv lock --check`; do not silently refresh `uv.lock` during an audit.
3. Ensure uv, Ruff, and ty target settings agree with `requires-python` and the supported source surface.
4. Map changed files to build, install, import, entry-point, optional-feature, platform, or native-extension risks.
5. Run the smallest relevant Ruff and ty checks through repository recipes or `uv run --locked`.
6. Use `uv build` to produce the wheel and sdist when artifact semantics changed.
7. Inspect artifacts, install the wheel into an isolated uv environment outside the checkout, and exercise the affected public consumer.
8. Report proven configurations separately from declared but untested support.

Ruff and ty are source/configuration evidence; neither substitutes for building and installing the distribution.

## uv Project And Locking Semantics

Check:

- `[project]`, dependency groups, optional dependencies, scripts, entry points, and `[tool.uv]` express distinct runtime, development, and source-resolution concerns
- `uv.lock` is current, committed when repository policy requires it, and resolves the declared marker space
- locked development packages are not mistaken for published runtime dependencies
- `uv run --locked` or equivalent recipes fail on stale metadata instead of rewriting the lock during CI validation
- exact/minimal syncs do not rely on undeclared ambient packages
- workspaces, local sources, and editable members do not leak into release artifacts unintentionally
- platform, architecture, implementation, and Python-version markers agree with reachable code paths

Do not use a successful rich development sync as evidence that minimal or optional installations work.

## Packaging And Installation

Check:

- build requirements and backend configuration are complete and mutually consistent
- package discovery, namespace packages, and source layout include the intended modules
- wheels and sdists contain required modules, type information, templates, schemas, licenses, and package data
- imports do not succeed only because the repository root is on `sys.path`
- generated version/source files exist in clean builds without untracked state
- editable installs do not mask failures in built artifacts
- package resources replace source-relative file access
- build hooks do not depend on ambient executables, network, working directory, locale, or machine paths without an explicit contract

Compare wheel and sdist contents when either could diverge. Test the built wheel from outside the repository.

Inspect archives and metadata with uv, platform archive tools, the standard library, or an existing repository validator. Do not add one-off packaging checker dependencies when direct inspection provides the required evidence.

## Ruff And ty Alignment

Check that Ruff's target version, selected rules, exclusions, import policy, and formatter configuration match the supported Python surface. Run lint before format checking when import sorting or fixable lint rules are part of the repository contract.

Check that ty discovers the installed packages and source roots intended by the project, targets a compatible Python version, includes public modules, and does not pass only because the checkout exposes undeclared import paths or development dependencies.

Treat tool suppressions and per-file exclusions as configuration-sensitive behavior. Route policy quality to production or tooling review when it is not specifically a portability issue.

## Runtime, Platform, And Consumer Matrix

Review syntax, standard-library APIs, typing syntax, and deprecations against the declared minimum Python version. Check claimed CPython, PyPy, free-threaded, operating-system, architecture, path, case-sensitivity, permission, encoding, locale, timezone, binary-format, and native-library behavior only where the repository declares or exercises it.

Check console/plugin entry points, public imports, optional-feature failures, metadata lookup, and package resources after wheel installation. Validate a minimal external consumer when the public import surface or installation contract changes.

For native components, check wheel tags, ABI/runtime requirements, shared-library discovery, build isolation, representation boundaries, and explicit unsupported-platform failures. Route native algorithm correctness to the owning language specialist.

Exercise only the configurations needed to distinguish the risk. Use uv's interpreter/environment selection rather than adding a second matrix runner, and record unavailable runtimes or platforms as evidence gaps.

## Focused Validation

Prefer repository recipes. Otherwise select from:

- `uv lock --check`
- `uv run --locked ruff check .`
- `uv run --locked ruff format --check .`
- `uv run --locked ty check`
- `uv build`
- artifact inspection followed by an isolated uv wheel install
- external import, entry-point, extra, and package-resource smoke tests
- a targeted supported-Python or platform configuration through uv

Do not upgrade dependencies or rewrite the lockfile unless the user requested that change. Request approval when uv needs unavailable network access or cache writes outside the sandbox.

## Output

Lead with build or portability blockers. For each finding, identify the affected artifact/configuration, the declared contract, and the smallest correction. End with uv/Ruff/ty commands run, artifacts and configurations validated, external-consumer evidence, remaining matrix gaps, and tooling or test-quality handoffs.
