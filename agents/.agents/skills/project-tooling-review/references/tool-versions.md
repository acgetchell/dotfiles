# Tool Version Review

Use this reference for tool-version drift across local installers, lockfiles, GitHub Actions, and docs.

## Ground Rules

- Do not claim a tool is latest from memory. Verify currentness through live authoritative sources or local package-manager metadata.
- Do not install, upgrade, uninstall, or run update commands unless the user explicitly asks.
- Keep "currentness" separate from "consistency." A repo can be internally consistent while not latest, and that is often acceptable.
- Prefer the repository's existing tool manager. Do not introduce a new manager just to solve one pin.

## Surfaces To Inspect

- `Brewfile`, `.Brewfile`, install scripts, and stow/bootstrap docs.
- `pyproject.toml`, `uv.lock`, `requirements*.txt`, `.python-version`, `tox.ini`, `noxfile.py`, and Python tool config.
- `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `.cargo/**`, cargo install recipes, and Rust tool docs.
- `.github/workflows/**` action versions and setup steps.
- `justfile` recipes that install, update, check, or invoke tools.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/dev/**`, and release docs that mention tool versions or commands.

## Consistency Checks

- Local and CI tool versions should agree when reproducibility matters.
- Docs should not tell maintainers to install a different version than workflows or lockfiles use.
- Recipes should invoke tools through the intended manager (`uv run`, `cargo`, Homebrew path, project-local script) rather than relying on accidental PATH order.
- Lockfiles should be updated when dependency declarations change.
- Version pins should have an update path, especially for Actions, cargo-installed binaries, and tools not covered by a lockfile.

## Currentness Checks

Use the source appropriate to the tool:

- Homebrew tools: `brew info`, `brew outdated`, or Homebrew JSON metadata when available.
- `uv`: official releases, package-manager metadata, or the installed `uv --version` plus the manager that installed it.
- Python packages: `uv lock --upgrade-package <name>` preview workflows, `uv tree`, package index metadata, or repository-approved commands.
- Rust toolchain: `rustup show`, `rustup check`, `rust-toolchain.toml`, and official channel metadata.
- Cargo-installed tools: `cargo install --list`, `cargo search <crate> --limit 1`, `cargo install-update -l` when installed, or crates.io metadata.
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
- `uv lock --check`, `uv tree`, or repository `uv` recipes for Python environments.
- `cargo tree`, `cargo metadata`, `cargo install --list`, or repository cargo-tool recipes for Rust tooling.
- `rustup show` and `rustup check` for Rust toolchain status.
- `just --summary` plus relevant check recipes for command-surface consistency.

Do not run update/install recipes, `brew upgrade`, `uv lock --upgrade`, `cargo update`, or `rustup update` unless the user explicitly asks.
