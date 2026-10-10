---
name: rust-cli-design
description: "Design or review Rust CLI behavior and library/CLI packaging, with validated arguments and deliberate dependency isolation."
---

# Rust CLI Design

Use this skill to design or audit Rust CLIs that sit beside reusable libraries. Prefer small, idiomatic binaries that parse raw arguments at the edge, convert them into validated command/config types, and keep CLI-only dependencies out of normal library builds.

## Core Decision

First decide whether the crate is primarily a library or an application.

- For a reusable library crate, make the CLI optional. Gate CLI-only dependencies and the binary behind a `cli` feature so downstream library users do not compile `clap`, plotting, JSON/reporting, notebook, telemetry, or simulation dependencies unless they opt in.
- For an application crate, an always-on CLI can be appropriate. Still keep raw clap DTOs separate from validated runtime config.
- For notebook workflows in a library crate, treat the CLI as the notebook execution boundary and document that notebooks require `--features cli`.

## Packaging and Examples

For a companion library CLI, keep CLI-only dependencies optional, gate the binary
with `required-features`, and ensure the package includes its sources. A separate
binary crate can provide the same isolation. Keep the established file layout
unless it obscures ownership or responsibilities.

Read [packaging and parsing examples](references/implementation-examples.md)
when adding a binary target or designing its argument-to-domain boundary.

## Parse-Don't-Validate Boundary

Raw clap structs are DTOs. Do not pass them into computation.

Parse raw arguments into an opaque validated command before execution. Keep
process exit/output handling at the edge and let terminal runners accept the
validated command.

Validation rules:

- Convert raw positive counts into `NonZero*` or stronger domain types before storing them in validated config.
- Convert dimension strings or numbers into enums or const-generic command variants before execution.
- Store only accepted paths, modes, counts, and output options in validated config.
- Keep passive report/output DTOs flat and serializable; do not reuse them as validated inputs.
- Choose error-enum exhaustiveness from the public compatibility policy. A module boundary alone does not require `#[non_exhaustive]`; adding it to an already published exhaustive enum can break callers.

## Fluent API Lens

Use fluent staging when it clarifies argument parsing and execution; it does not
require exposing an intermediate public stage without caller value.

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

After changing CLI packaging or parse boundaries, choose the smallest
non-overlapping set of checks that covers the affected contracts. The following
are candidate checks, not a mandatory sequence:

```bash
cargo check --no-default-features
cargo check --features cli --bin <name>
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo run --features cli --bin <name> -- --help
```

Also smoke-test at least one successful command and one rejected invalid argument path. For notebook-backed CLIs, execute or lint the notebook through the repository's notebook validator.

Avoid a ladder of overlapping test tiers solely for reassurance. Run focused
red/green checks when useful during a fix, then any required final aggregate gate
on the final source state even if it repeats those checks. Record the reason for
overlap without counting it as independent evidence. Reuse valid evidence where
the required validation contract permits it; overlap alone requires no approval
or command-surface escalation.
