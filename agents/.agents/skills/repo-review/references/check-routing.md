# Check Routing

Use this reference after reading the requested scope and before selecting focused orchestrators.

## Scope Discovery

Default to branch scope. The normal workflow is to make a branch, review the whole branch, and include any staged, unstaged, or untracked work still sitting on top of it.

Use whole-repo baseline scope when the user explicitly asks for phrases such as "whole-repo baseline", "baseline checkpoint", "clean repo checkpoint", "full repo review as-is", "review everything as it is", "repo-wide audit against a clean repo", or equivalent. In baseline mode, review tracked repository files even when there is no diff.

Use read-only discovery commands:

- Identify the branch: `git --no-pager branch --show-current`.
- Use an explicit user-provided or PR-provided base when available.
- Otherwise infer the default-branch base from `origin/HEAD`, `origin/main`, `origin/master`, `main`, or `master`, in that order when present.
- Do not use the branch's same-name tracking upstream as the review base; that narrows a pushed feature branch to only unpushed local changes.
- Find the merge base: `git --no-pager merge-base HEAD <base>`.
- Inspect committed branch changes: `git --no-pager diff --name-status <merge-base>...HEAD` and `git --no-pager diff <merge-base>...HEAD`.
- Inspect the full local branch state, including staged and unstaged work: `git --no-pager diff --name-status <merge-base>` and `git --no-pager diff <merge-base>`.
- Include untracked files with `git --no-pager status --short` and `git ls-files --others --exclude-standard`.

Use staged-only, changed-worktree-only, or whole-repo baseline scope only when the user explicitly asks for that scope. If the branch base cannot be inferred, report the ambiguity and fall back to the current changed files only after making that limitation visible.

For release-readiness review, keep branch scope for code and tooling but expand the documentation slice to every tracked active document in the scientific crate. Exclude `docs/archive/**` and equivalent designated archive trees unless explicitly requested, classify generated or otherwise excluded non-archive documentation, and do not let an unchanged active file escape release review merely because it is absent from the diff.

## Whole-Repo Baseline Inventory

For baseline checkpoints, build a tracked-file inventory instead of a diff:

- List tracked files with `git ls-files`.
- Exclude ignored, generated, dependency, cache, and build-output paths by relying on tracked files and local repository conventions.
- Include a concise inventory count by surface: Rust, Python, project tooling, docs/examples, notebooks, generated/fixtures when relevant.
- Select orchestrators from repository surfaces that are present, not from changed files.
- Hand each selected orchestrator the relevant tracked-file subset and state that this is whole-repo baseline mode.
- If the repository is clean, say so, but do not treat a clean worktree as "nothing to review."
- If the worktree is not clean and the user asked for a clean-repo checkpoint, report the dirty state and ask whether to review the current working tree or wait for a clean checkout.

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

Select `docs-review-orchestrator` for:

- coupled scientific-crate documentation such as `README.md`, `REFERENCES.md`, `CITATION.cff`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `docs/**`
- Rust API or module docs when documentation is a material review surface, especially in a docs-only request
- release metadata, version/documentation synchronization, algorithm or invariant descriptions, benchmark/coverage documentation, roadmap state, and scientific-crate publication/release guidance
- references, DOI or source links, algorithm provenance, scientific claims, or citation metadata
- whole-repo baseline mode when the tracked inventory contains an active documentation suite

In whole-repo baseline mode, select an orchestrator when any of its surfaces are present in the tracked-file inventory. Record absent surfaces as skipped in the `Review Evidence` table.

## Shared Files

Route shared files to all affected owners:

- `Cargo.toml` with dependency, feature, lint, or MSRV changes: Rust plus project tooling.
- `pyproject.toml` with dependency groups, entry points, lint config, or project scripts: Python plus project tooling.
- `uv.lock` or `Cargo.lock`: language review for dependency impact and tooling review for version/update discipline.
- `justfile`: project tooling first; add Rust or Python when recipe semantics change which language checks run.
- `.github/workflows/**`: project tooling first; add Rust or Python when matrices, toolchains, or validation coverage change.
- Docs with commands and examples: project tooling for command truth, language orchestrators for API or behavior truth.
- Coupled scientific-crate docs and release metadata: docs review for cross-document truth; retain tooling and language owners for the commands and behavior those docs describe. Generic skill, command, CI, and maintainer-process documentation remains with project tooling.

## Ordering

Use the smallest order that preserves validation integrity:

1. Project tooling first when tool versions, recipes, workflows, or command docs may affect validators.
2. Rust next when Rust-owned behavior or crate metadata changed.
3. Python next when Python-owned behavior, notebooks, or Python config changed.
4. Documentation after source-owning passes establish the behavior and claims the docs must reflect.
5. Project tooling again only when language or documentation passes changed commands, workflow files, lockfiles, or command docs.
6. Final synthesis after all selected validators pass or known blockers are documented.

Pass the same branch-scope file list and diff to every selected orchestrator in branch mode. In baseline mode, pass the relevant tracked-file inventory subset and explicitly say "whole-repo baseline mode." Do not let a focused orchestrator silently re-scope the review to only staged or unstaged changes unless the user requested that narrower scope.

## Validation Choice

Let each selected orchestrator choose focused validators from its own routing guidance. At the meta level, check whether the combined change needs stronger validation:

- In baseline mode, prefer non-mutating structural and test validators that characterize the current repository health. Do not run expensive benchmark, release, publish, or ecosystem-update validators unless the user explicitly asks.
- If only one surface changed, keep that surface's focused validator.
- If language code and command wiring changed together, run the focused language validator and the focused tooling validator.
- If workflows changed, prefer local structural validation such as YAML parsing, `actionlint`, `zizmor`, or repository recipes when available.
- If lockfiles, toolchain pins, or latest-version claims changed, verify with live authoritative sources or local package-manager metadata before declaring them current.
- Escalate to full CI only when cross-surface changes make focused validators insufficient or repository instructions require it.

If a validator needs network access, installation, or approval, run the strongest local read-only substitute and report the gap.
