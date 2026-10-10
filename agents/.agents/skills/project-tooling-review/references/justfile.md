# justfile Review

Use this reference for `justfile` changes, command-surface docs, and recipes that define how maintainers run local workflows.

## Review Focus

- Prefer a small command vocabulary over many one-off recipes. Common tiers are `check`, `check-fast`, `fix`, `ci`, `test-*`, `lint-*`, `coverage`, `docs`, `bench-*`, `release-*`, and project-specific smoke checks.
- Keep `just` as the command memory layer. Workflows and docs should call recipes instead of duplicating long `cargo`, `uv`, `taplo`, `actionlint`, `typos`, or notebook commands.
- Recipe names should describe maintainer intent, not the implementation tool, unless the recipe is a direct tool wrapper such as `action-lint` or `toml-fmt-check`.
- Separate fixers from checks. A recipe named `check` or `ci` should not mutate tracked files; a recipe named `fix` should make mutations explicit.
- Separate fast local checks from full CI and slow/performance/release checks.
- Trace the execution order of canonical aggregate gates, including nested dependencies and recipe-body calls. Flag avoidable expensive execution before inexpensive static failures; account for true generation/setup prerequisites before moving a check earlier.
- Preserve recipe composability. Prefer recipes that call other recipes over copy-pasted command sequences when the same workflow appears in multiple places.
- Ensure aggregate recipes do not execute the same underlying test selection more than once through overlapping dependencies or nested recipe calls. A broader recipe should add distinct evidence, not replay already completed checks.
- Prefer composable aggregate gates when useful, but retain required final gates even after focused red/green tests. Record unavoidable overlap; an indivisible gate is not itself a defect. Repetition inside one aggregate remains distinct from justified iteration followed by a final gate.

## Fail-Fast Dependency Order

For ordinary sequential dependencies, this graph reaches notebook lint only
after the Python tests finish:

```just
ci: python-tests notebook-check
notebook-check: notebook-lint
    uv run jupyter execute analysis.ipynb
```

Move the cheap check into the canonical aggregate's early dependencies while
retaining it on the standalone notebook gate:

```just
ci: notebook-lint python-tests notebook-check
notebook-check: notebook-lint
    uv run jupyter execute analysis.ipynb
```

Within this invocation, Just coalesces the shared `notebook-lint` dependency
with the same arguments: lint runs once, before tests, and `notebook-check`
executes the notebook afterward. A separate `just notebook-lint` process in a
recipe body does not share that dependency execution state. Inspect arguments,
separate invocations, and parallel attributes before claiming coalescing or a
guaranteed order.

Preserve real prerequisites: if lint needs an exported notebook module or
generated stubs, keep that generation before lint. Expensive integration tests
that produce no lint input are an avoidable predecessor. Do not move a check
ahead of setup it needs or drop execution checks to make feedback faster.

The executable examples in
[`scripts/fixtures/late-static.just`](../scripts/fixtures/late-static.just) and
[`scripts/fixtures/early-static.just`](../scripts/fixtures/early-static.just)
use harmless markers and an injectable lint failure. Their tests verify early
failure, one shared lint execution, and the required export-before-lint order,
including success and failure of the standalone notebook gate.

Change the repository's canonical recipe rather than adding a review-only
precheck. Report an ordering need to the validator owner when dispatch commands
are already fixed. After a repair, reuse successful evidence only after the
existing exact identity/dependency checks; resume affected and unexecuted
components without replaying unaffected tests.

## Tool Install Recipes

If `justfile` installs, upgrades, checks, or asserts versions for tools managed by `uv tool`, `cargo install`, Homebrew, or another manager, keep those recipes synchronized with the updated managed-tool versions.

Check for:

- recipe variables such as `<tool>_version` or `<tool>-version`
- inline install specs such as `cargo install --version`, `uv tool install name@version`, `brew install`, `pipx install name==version`, or setup helper arguments
- ensure/check recipes that compare `tool --version` output against a pinned value
- recipes that call bootstrap scripts or workflows with version arguments

When `project-tooling-review` updates a managed tool, update matching `justfile` pins in the same pass before validating workflows. The local command surface should install and assert the same version that GitHub Actions and bootstrap scripts use.

When the `justfile` owns a pin, prefer `just --evaluate <variable>` wherever `just` is
already available. This preserves Just's parsing and interpolation semantics and avoids
independent workflow variables, duplicated literals, or brittle `grep`/`cut` parsing.
Bootstrapping `just` itself is the exception: a consumer that must install `just`
before it can evaluate the file needs a documented pre-Just extraction path. Centralize
that path in a repository-local helper or composite action when multiple consumers need
it, and make it tolerate the Justfile's supported whitespace, comments, and quoting
while failing clearly on a missing or empty value.

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
- managed tool inventories from `uv tool list`, `cargo install --list`, and `cargo install-update -l`
- scripts that are invoked by recipes

Flag docs or workflows that mention deleted/renamed recipes, skip new required recipes, or describe different command arguments than the recipe actually accepts.

## Validators

Use repository guidance first. Otherwise prefer:

- `just --list` or `just --summary` to confirm recipes parse and are discoverable.
- `just --fmt --check` when the installed `just` supports it.
- `just --dry-run <recipe>` for safe recipe expansion checks when arguments are known.
- The narrow changed recipe's check command when it is safe and local.

Do not run destructive, publishing, release, or update recipes unless the user explicitly asks.
