---
name: rust-cli-design
description: Design, build, or review Rust command-line interfaces for library crates and scientific tooling. Use when a task touches Cargo binary packaging, optional CLI features, clap/argument parsing, parse-don't-validate CLI boundaries, notebook-driven CLI workflows, CLI README quickstarts, or whether a Rust CLI should be optional or always-on.
---

# Rust CLI Design

Use this skill to design or audit Rust CLIs that sit beside reusable libraries. Prefer small, idiomatic binaries that parse raw arguments at the edge, convert them into validated command/config types, and keep CLI-only dependencies out of normal library builds.

## Core Decision

First decide whether the crate is primarily a library or an application.

- For a reusable library crate, make the CLI optional. Gate CLI-only dependencies and the binary behind a `cli` feature so downstream library users do not compile `clap`, plotting, JSON/reporting, notebook, telemetry, or simulation dependencies unless they opt in.
- For an application crate, an always-on CLI can be appropriate. Still keep raw clap DTOs separate from validated runtime config.
- For notebook workflows in a library crate, treat the CLI as the notebook execution boundary and document that notebooks require `--features cli`.

## Cargo Shape

For optional CLIs in library crates, prefer this manifest shape:

```toml
[package]
autobins = false

[dependencies]
clap = { version = "...", features = ["derive"], optional = true }
serde_json = { version = "...", optional = true }

[features]
cli = ["dep:clap", "dep:serde_json"]

[[bin]]
name = "crate-name"
path = "src/main.rs"
required-features = ["cli"]
```

Checklist:

- Put CLI-only dependencies in `[dependencies]` as `optional = true` when the binary needs them.
- Keep benchmark-only or test-only dependencies in `[dev-dependencies]`.
- Avoid compatibility feature aliases unless an existing published API needs them.
- Use `required-features = ["cli"]` on the binary so `cargo build` for library users does not build the CLI accidentally.
- Keep package `include` broad enough to publish `src/main.rs` and any CLI config module if the binary is part of the release artifact.

## File Shape

Prefer the simple two-file binary shape unless the CLI grows enough to justify more:

- `src/main.rs`: process entrypoint only
- `src/config.rs`: clap DTOs, validated command/config types, typed CLI errors, and terminal runner

Avoid nested `src/bin/<name>/support.rs` trees for a single companion CLI unless there are multiple binaries or genuinely independent modules.

## Parse-Don't-Validate Boundary

Raw clap structs are DTOs. Do not pass them into computation.

Prefer this process boundary:

```rust
fn main() -> ExitCode {
    config::CliArgs::from_args()
        .into_validated()
        .and_then(|command| config::run(&command))
        .map_or_else(config::exit_with_error, |()| ExitCode::SUCCESS)
}
```

In `config.rs`, use raw args only at the edge:

```rust
#[derive(Debug, Parser)]
pub struct CliArgs {
    #[command(subcommand)]
    command: CommandArgs,
}

impl CliArgs {
    pub fn from_args() -> Self {
        Self::parse()
    }

    pub fn into_validated(self) -> Result<ValidatedCommand, CliError> {
        Ok(ValidatedCommand(self.command.into_validated()?))
    }
}
```

Then make the validated command opaque:

```rust
#[derive(Debug)]
pub struct ValidatedCommand(Command);

pub fn run(command: &ValidatedCommand) -> Result<(), CliError> {
    match &command.0 {
        Command::Generate(config) => run_generate(config),
        Command::Stress(config) => run_stress(config),
    }
}
```

Validation rules:

- Convert raw positive counts into `NonZero*` or stronger domain types before storing them in validated config.
- Convert dimension strings or numbers into enums or const-generic command variants before execution.
- Store only accepted paths, modes, counts, and output options in validated config.
- Keep passive report/output DTOs flat and serializable; do not reuse them as validated inputs.
- Make public error enums `#[non_exhaustive]` when they cross a module or crate boundary.

## Fluent API Lens

Use fluent staging where it clarifies the boundary:

```rust
CliArgs::from_args()
    .into_validated()
    .and_then(|command| run(&command))
```

Do not force internal runners into chains. Once validation has produced a proof-bearing command, named terminal functions such as `run_generate`, `run_stress`, `write_json_output`, or `emit_report` are clearer than deeply chained closures.

## CLI Output

For binaries, stdout/stderr writes are appropriate user-facing IO. If a repository bans `println!` or `eprintln!` in `src/`, use explicit locked handles:

```rust
let stdout = std::io::stdout();
let mut handle = stdout.lock();
writeln!(handle, "...")?;
```

Use stdout for machine-readable telemetry and requested artifacts. Use stderr for process-level errors.

## README Guidance

Keep the main README Quickstart aligned with the crate's primary audience.

- For a reusable library crate, make the first Quickstart library-only and avoid requiring CLI features.
- Add a separate `CLI Quickstart`, `Notebook Quickstart`, or `CLI/Notebook Quickstart` when notebooks or diagnostics call the binary.
- In that subsection, explicitly show `--features cli` or the `just` recipe that enables it.
- Say that the CLI feature pulls in CLI/notebook dependencies so library users can opt out.
- Do not let notebook-first docs imply that ordinary library use needs CLI dependencies.

## Validation

After changing CLI packaging or parse boundaries, run focused checks before full CI:

```bash
cargo check --no-default-features
cargo check --features cli --bin <name>
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo run --features cli --bin <name> -- --help
```

Also smoke-test at least one successful command and one rejected invalid argument path. For notebook-backed CLIs, execute or lint the notebook through the repository's notebook validator.
