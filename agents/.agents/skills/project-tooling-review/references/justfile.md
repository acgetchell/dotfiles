# justfile Review

Use this reference for `justfile` changes, command-surface docs, and recipes that define how maintainers run local workflows.

## Review Focus

- Prefer a small command vocabulary over many one-off recipes. Common tiers are `check`, `check-fast`, `fix`, `ci`, `test-*`, `lint-*`, `coverage`, `docs`, `bench-*`, `release-*`, and project-specific smoke checks.
- Keep `just` as the command memory layer. Workflows and docs should call recipes instead of duplicating long `cargo`, `uv`, `taplo`, `actionlint`, `typos`, or notebook commands.
- Recipe names should describe maintainer intent, not the implementation tool, unless the recipe is a direct tool wrapper such as `action-lint` or `toml-fmt-check`.
- Separate fixers from checks. A recipe named `check` or `ci` should not mutate tracked files; a recipe named `fix` should make mutations explicit.
- Separate fast local checks from full CI and slow/performance/release checks.
- Preserve recipe composability. Prefer recipes that call other recipes over copy-pasted command sequences when the same workflow appears in multiple places.

## Safety Checks

- Destructive recipes require explicit arguments and should not hide behind friendly names.
- Avoid broad deletes. If cleanup is necessary, scope it to known build/output directories and quote paths.
- Recipes that rely on shell features should use a clear shell setting or script block according to local convention.
- Commands should fail on the first real failure. Watch for `|| true`, ignored exit codes, pipelines without failure handling, and swallowed subprocess errors.
- Recipes should not rely on the user's current directory when the repository root matters.
- Secrets and tokens should not appear in command echo, logs, or generated files.

## Drift Checks

Compare `justfile` against:

- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `docs/dev/**`
- `.github/workflows/**`
- language-specific config such as `pyproject.toml`, `Cargo.toml`, `rust-toolchain.toml`, and lockfiles
- scripts that are invoked by recipes

Flag docs or workflows that mention deleted/renamed recipes, skip new required recipes, or describe different command arguments than the recipe actually accepts.

## Validators

Use repository guidance first. Otherwise prefer:

- `just --list` or `just --summary` to confirm recipes parse and are discoverable.
- `just --fmt --check` when the installed `just` supports it.
- `just --dry-run <recipe>` for safe recipe expansion checks when arguments are known.
- The narrow changed recipe's check command when it is safe and local.

Do not run destructive, publishing, release, or update recipes unless the user explicitly asks.

