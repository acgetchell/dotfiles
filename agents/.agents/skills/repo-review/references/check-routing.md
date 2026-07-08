# Check Routing

Use this reference after reading the requested scope and before selecting focused orchestrators.

## Scope Discovery

Choose read-only discovery commands that match the request:

- Staged review: `git --no-pager diff --cached --name-status` and `git --no-pager diff --cached`.
- Changed worktree review: `git --no-pager status --short`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Branch or PR-style review: inspect the branch diff against the appropriate base without mutating git state.

If scope is ambiguous, prefer the current changed files over a whole-repo baseline.

## Surface Matrix

Select `rust-review-orchestrator` for:

- `src/**/*.rs`, `tests/**/*.rs`, `benches/**/*.rs`, `examples/**/*.rs`
- Rust doctests, examples, public API docs, `README` Rust examples, or crate docs
- `Cargo.toml`, `Cargo.lock`, `.cargo/**`, `rust-toolchain*`, `clippy.toml`, `rustfmt.toml`
- workflows or recipes that change Rust validation, feature flags, benchmarks, releases, or coverage

Select `python-review-orchestrator` for:

- `*.py`, `scripts/**/*.py`, `tests/**/*.py`, Python packages, Python fixtures, and generated Python utilities
- `.ipynb`, notebook runners, notebook dependency groups, and rendered notebook workflows
- `pyproject.toml`, `uv.lock`, requirement files, pytest/ruff/mypy/pyright/coverage configuration
- workflows or recipes that change Python validation, release helpers, notebooks, or coverage

Select `project-tooling-review` for:

- `justfile`, `Makefile`, shell command wrappers, and local validator tiers
- `.github/workflows/**`, action versions, CI permissions, caches, matrices, and status-check wiring
- `Brewfile`, tool installer docs, `uv tool`, `cargo install`, `rustup`, language toolchain pins, and update workflows
- `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `docs/**`, or changelog text that describes command surfaces, CI, tools, or maintainer workflow
- semgrep, actionlint, zizmor, markdown, YAML, TOML, and release configuration

## Shared Files

Route shared files to all affected owners:

- `Cargo.toml` with dependency, feature, lint, or MSRV changes: Rust plus project tooling.
- `pyproject.toml` with dependency groups, entry points, lint config, or project scripts: Python plus project tooling.
- `uv.lock` or `Cargo.lock`: language review for dependency impact and tooling review for version/update discipline.
- `justfile`: project tooling first; add Rust or Python when recipe semantics change which language checks run.
- `.github/workflows/**`: project tooling first; add Rust or Python when matrices, toolchains, or validation coverage change.
- Docs with commands and examples: project tooling for command truth, language orchestrators for API or behavior truth.

## Ordering

Use the smallest order that preserves validation integrity:

1. Project tooling first when tool versions, recipes, workflows, or command docs may affect validators.
2. Rust next when Rust-owned behavior or crate metadata changed.
3. Python next when Python-owned behavior, notebooks, or Python config changed.
4. Project tooling again only when the language passes changed commands, workflow files, lockfiles, or docs.
5. Final synthesis after all selected validators pass or known blockers are documented.

## Validation Choice

Let each selected orchestrator choose focused validators from its own routing guidance. At the meta level, check whether the combined change needs stronger validation:

- If only one surface changed, keep that surface's focused validator.
- If language code and command wiring changed together, run the focused language validator and the focused tooling validator.
- If workflows changed, prefer local structural validation such as YAML parsing, `actionlint`, `zizmor`, or repository recipes when available.
- If lockfiles, toolchain pins, or latest-version claims changed, verify with live authoritative sources or local package-manager metadata before declaring them current.
- Escalate to full CI only when cross-surface changes make focused validators insufficient or repository instructions require it.

If a validator needs network access, installation, or approval, run the strongest local read-only substitute and report the gap.
