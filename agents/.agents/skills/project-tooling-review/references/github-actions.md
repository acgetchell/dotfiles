# GitHub Actions Review

Use this reference for `.github/workflows/**`, reusable workflow calls, Actions-related docs, and CI command wiring.

## Review Focus

- Workflows should call canonical `just` recipes when the repository standardizes on `just`; avoid duplicating long local command strings in YAML.
- Workflow names, job names, and required status checks should remain stable unless the change intentionally updates branch protection or release policy.
- Triggers should match intent: `pull_request` for PR validation, `push` for protected branches or release branches, `workflow_dispatch` for manual runs, and scheduled runs only when maintenance value justifies noise.
- Permissions should be least-privilege. Prefer top-level `permissions: contents: read` and elevate only specific jobs that need writes, packages, pages, OIDC, or checks.
- Concurrency should cancel redundant PR runs when safe, but not cancel release/publish jobs that must complete.
- Matrix strategy should cover declared supported versions and platforms without exploding cost accidentally.
- Caches should key on lockfiles and toolchain files, not only broad branch names. Cache restore should not hide dependency drift.
- Artifacts should have clear names, bounded retention, and no secrets or oversized generated clutter.

## Version And Pinning Checks

- Verify action versions against live releases when the user asks for currentness or when changing versions. Do not rely on model memory for latest action versions.
- Prefer major-version pins such as `actions/checkout@v4` for routine maintenance unless the repository has a stricter supply-chain policy.
- Prefer commit SHA pins for high-security/release/signing workflows when that policy exists, and document the update path.
- Keep action versions consistent across workflows unless a workflow intentionally needs a different major version.

## Managed Tool Version Propagation

When `project-tooling-review` updates a tool managed by `uv tool` or `cargo install`, check whether GitHub Actions installs or invokes that tool. Update workflow pins in the same pass when the workflow depends on the updated version.

Check for:

- workflow `env` pins such as `UV_VERSION`, `JUST_VERSION`, `ZIZMOR_VERSION`, or other `<TOOL>_VERSION` values
- setup action inputs such as `version: ${{ env.UV_VERSION }}` or literal version strings
- cargo-install cache actions with `tool: name@version`
- inline `cargo install --version`, `uv tool install name@version`, `pipx install name==version`, or equivalent install commands
- comments next to pinned tool versions when they are used as human-readable version markers

Keep the action pin and managed tool pin separate. For example, updating `zizmor` should update `ZIZMOR_VERSION` or `tool: zizmor@...`; it should not update `taiki-e/cache-cargo-install-action@...` unless that action itself is stale. Updating `uv` should update the setup action's requested `uv` version; it should not update `astral-sh/setup-uv@...` unless the setup action itself is stale.

If the workflow reads the version from a single env var or bootstrap script constant, update that source of truth rather than duplicating literal versions throughout the workflow. Keep local bootstrap pins, workflow pins, and command docs synchronized.

When the repository declares pins as `justfile` variables, resolve them after `just`
installation with `just --evaluate <variable>` and publish the results through step
outputs or environment files as needed. Avoid copying those values into workflow-level
`env` entries or parsing the Justfile with `grep`/`cut`. A workflow may use a dedicated
pre-Just resolver only for the `just` version required to bootstrap the evaluator.
When multiple workflows need it, prefer a checked-in composite action that parses and
validates the declaration, installs the pinned `just`, exposes the resolved version as
an output, and keeps the bootstrap logic in one place. After that action, export all
other evaluated pins together through `$GITHUB_OUTPUT` or `$GITHUB_ENV`.

## Drift Checks

Compare workflows against:

- `justfile` recipe names and arguments
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `docs/dev/**`
- `Brewfile`, `pyproject.toml`, `uv.lock`, `Cargo.toml`, `rust-toolchain.toml`, and other toolchain files
- `uv tool` and `cargo install` managed CLI inventories and updated local versions
- branch protection or required check naming when available

Flag workflows that run stale recipes, bypass canonical local checks, silently skip failures, or publish artifacts without matching release docs.

## Validators

Use repository guidance first. Otherwise prefer:

- `actionlint` or `just action-lint` when available.
- YAML linting when actionlint is unavailable.
- `gh workflow view` or `gh api` for live workflow metadata only when needed and available.
- A targeted dry run with `act` only when the repository already supports it and local secrets are not required.

Do not trigger remote workflow runs, publish releases, upload artifacts, or mutate repository settings unless the user explicitly asks.
