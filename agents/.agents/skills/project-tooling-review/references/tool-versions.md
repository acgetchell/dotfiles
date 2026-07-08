# Tool Version Review

Use this reference for tool-version drift across local installers, lockfiles, GitHub Actions, and docs.

## Ground Rules

- Do not claim a tool is latest from memory. Verify currentness through live authoritative sources or local package-manager metadata.
- Do not install or uninstall unrelated tools unless the user explicitly asks. When the requested scope includes tool-version currentness, update drift, or "latest" tooling review, update stale tools through the repository's existing manager.
- Keep "currentness" separate from "consistency." A repo can be internally consistent while not latest, and that is often acceptable.
- Prefer the repository's existing tool manager. Do not introduce a new manager just to solve one pin.

## Surfaces To Inspect

- `Brewfile`, `.Brewfile`, install scripts, and stow/bootstrap docs.
- `pyproject.toml`, `uv.lock`, `requirements*.txt`, `.python-version`, `tox.ini`, `noxfile.py`, and Python tool config.
- `uv tool` managed CLI tools, their install specs, docs, and workflow invocations.
- `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `.cargo/**`, cargo install recipes, and Rust tool docs.
- `cargo install` managed binaries, `cargo install-update` output, bootstrap pins, and workflow install specs.
- `.github/workflows/**` action versions and setup steps.
- `justfile` recipes that install, update, check, or invoke tools.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/dev/**`, and release docs that mention tool versions or commands.

## Local Tool Inventory

Before comparing a tool to repo pins or remote latest metadata, inspect the local tool that maintainers actually run:

- Resolve the executable with `command -v <tool>` or the repository's documented absolute path.
- Capture the installed version with `<tool> --version` or the tool's documented version command.
- Identify the owning manager when possible: Homebrew, `uv tool`, `cargo install`, `rustup`, system package manager, or standalone installer.
- Compare the installed version against docs, lockfiles, workflows, installer manifests, and update recipes.
- If a tool was just installed or upgraded locally, treat that local version as a currentness signal to reconcile rather than ignoring it because the changed files did not mention the tool.

For `uv` itself, always check `command -v uv` and `uv --version` first. If it is Homebrew-managed, also use Homebrew metadata such as `brew list --versions uv`, `brew info uv`, or Homebrew JSON metadata when available. Use `uv tool list` for tools installed by `uv`, not as the source of truth for the `uv` executable's own version.

For tools managed by `uv tool`, run `uv tool list` before updating. When version updates are in scope, run `uv tool upgrade --all` or `uv tool upgrade <name>` for targeted review, then run `uv tool list` again and record before/after versions. If a `uv tool` command needs network or cache access, request approval rather than substituting a global Python install.

For tools managed by `cargo install`, run `cargo install --list` and `cargo install-update -l` before updating. When version updates are in scope, run `cargo install-update --all` or `cargo install-update <package>` for targeted review, preserving repository-required flags such as `--locked` when applicable. Run `cargo install --list` or `<tool> --version` after updating and record before/after versions.

## Version Source Of Truth

For managed CLI tool updates, reconcile versions in this order:

1. Owning manager state after update: installed version and manager metadata from `uv tool list`, `cargo install --list`, `<tool> --version`, Homebrew metadata, or the relevant manager.
2. Local command source of truth: `justfile` variables or install specs, bootstrap constants in `bin/**`, and repository installer scripts.
3. CI pins: `.github/workflows/**` environment variables, action inputs, inline install commands, and cache-install `tool: name@version` values.
4. Documentation: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/**`, and release notes that mention the tool version or update command.

Avoid creating duplicate independent pins. If one tracked file can read or call the repository's source of truth, prefer that over repeating literal versions. Keep project dependency lockfiles separate from managed CLI pins unless the user explicitly asks for dependency updates.

## Managed Tool Update Flow

Use this flow for `uv tool` and `cargo install` managed CLIs:

1. Inventory installed tools, versions, owning manager, and command paths.
2. Compare against authoritative latest metadata from the manager, package index, or registry.
3. Update stale tools with the owning manager when version updates are in scope.
4. Capture the new installed versions and note tools that were already current.
5. Search tracked files for each updated tool name and old version, including `justfile`, `.github/workflows/**`, `bin/**`, `README.md`, `AGENTS.md`, `docs/**`, `pyproject.toml`, and lockfiles.
6. Update repository pins that install or assert the tool version: `*_VERSION` environment variables, `cargo install --version`, `uv tool install <tool>@<version>`, action inputs, cache-install `tool: name@version` values, bootstrap constants, and docs.
7. If `justfile` installs, upgrades, checks, or asserts the updated tool, update the recipe version, recipe variable, or install spec in the same change. The command memory layer should install the same updated version the manager now reports.
8. If a GitHub Actions workflow uses the updated tool, update the workflow's pinned tool version in the same change. Do not confuse the workflow action version or SHA with the managed tool version; update action pins only when the action itself is stale.
9. Run focused validators for the touched tooling surface.

## Consistency Checks

- Local and CI tool versions should agree when reproducibility matters.
- Docs should not tell maintainers to install a different version than workflows or lockfiles use.
- Recipes should invoke tools through the intended manager (`uv run`, `cargo`, Homebrew path, project-local script) rather than relying on accidental PATH order.
- Lockfiles should be updated when dependency declarations change.
- Version pins should have an update path, especially for Actions, cargo-installed binaries, and tools not covered by a lockfile.

## Currentness Checks

Use the source appropriate to the tool for read-only currentness checks:

- Homebrew tools: `brew info`, `brew outdated`, or Homebrew JSON metadata when available.
- `uv`: installed `uv --version` plus the manager that installed it, then official releases or package-manager metadata for latest-version claims.
- `uv tool` managed tools: `uv tool list` and package index metadata when a non-mutating latest check is required; use the managed update flow above when version updates are in scope.
- Python packages: `uv lock --check`, `uv tree`, package index metadata, or repository-approved read-only commands. Do not mutate project dependency lockfiles during managed CLI update review unless the user explicitly asks for dependency updates.
- Rust toolchain: `rustup show`, `rustup check`, `rust-toolchain.toml`, and official channel metadata.
- Cargo-installed tools: `cargo install --list`, `cargo install-update -l`, `cargo search <crate> --limit 1`, or crates.io metadata; use the managed update flow above when version updates are in scope.
- GitHub Actions: action release pages, tags, GitHub API, or Dependabot/Renovate metadata if configured.

If network access or package-manager metadata is unavailable, report the check as local-only and name what remains unverified.

## Pinning Guidance

- Pin when reproducibility, CI stability, or supply-chain policy matters.
- Allow floating major versions when routine maintenance and upstream security patches are preferred.
- Avoid exact pins in docs if the true source of record is a lockfile or installer manifest.
- Keep generated lockfiles machine-readable and avoid hand-editing them unless the repository explicitly permits it.
- Treat version bumps as behavior changes when they alter formatter output, lints, generated docs, benchmark output, or CI behavior.

## Validators

Use repository guidance first. Otherwise prefer read-only checks:

- `brew bundle check` for Brewfile satisfaction when available.
- `uv lock --check`, `uv tree`, `uv tool list`, or repository `uv` recipes for Python environments and `uv tool` managed CLIs.
- `cargo tree`, `cargo metadata`, `cargo install --list`, `cargo install-update -l`, or repository cargo-tool recipes for Rust tooling.
- `rustup show` and `rustup check` for Rust toolchain status.
- `just --summary` plus relevant check recipes for command-surface consistency.

Do not run broad ecosystem updates such as `brew upgrade`, `uv lock --upgrade`, `cargo update`, or `rustup update` unless the user explicitly asks. `uv tool upgrade` and `cargo install-update` are in scope when reviewing managed CLI version drift.
