# Rust CLI Implementation Examples

Use these examples when designing CLI packaging or a parsing boundary. They are
illustrative shapes, not a required file layout.

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

One possible layout for a small companion binary is:

- `src/main.rs`: process entrypoint only
- `src/config.rs`: clap DTOs, validated command/config types, typed CLI errors, and terminal runner

Preserve an established layout when it keeps responsibilities clear. Additional binaries or independent modules can justify a different structure.

## Parse-Don't-Validate Example

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
