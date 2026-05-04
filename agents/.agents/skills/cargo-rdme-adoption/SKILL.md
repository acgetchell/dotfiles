---
name: cargo-rdme-adoption
description: "Standardize a Rust crate's docs.rs landing page and README using cargo-rdme, treating src/lib.rs //! as the single source of truth and auto-generating the README's API section. USE FOR: adopting cargo-rdme on a new or existing crate; producing a uniform docs.rs front page across multiple crates; migrating away from #![doc = include_str!(\"../README.md\")] / #![cfg_attr(any(doc, doctest), doc = include_str!(\"../README.md\"))]; restructuring src/lib.rs //! to be the canonical landing page (pitch + minimal doctest + concepts); reformatting README.md to the standard layout (badges → <!-- cargo-rdme --> marker → install/MSRV/features/contributing/license); adding cargo rdme --check to CI; adding docs-readme/docs-readme-check recipes to a justfile; producing a .cargo-rdme.toml when defaults are not enough. DO NOT USE FOR: writing substantive doc content (use crate-docs-update); commit messages (use changelog-commit-message); reviewing /// public-API doc sections (use rust-api-docs); Cargo.toml / feature flag / MSRV review (use rust-cargo-hygiene); non-Rust repositories; repositories that already correctly use cargo-rdme and only need content edits."
---

# cargo-rdme-adoption

Adopt cargo-rdme on a Rust crate so the **`src/lib.rs` `//!` block is the single source of truth** for both the docs.rs landing page and the README's API section, kept in sync by a CI gate.

This skill is about the mechanism (markers, `lib.rs` ↔ README sync, CI wiring) and the canonical layout. It is not about writing the substantive prose; for that, defer to `crate-docs-update`.

## The cargo-rdme model

cargo-rdme reads the crate-level `//!` doc comment from `src/lib.rs` and injects it into the README between cargo-rdme markers. The flow is:

- **Source of truth:** `src/lib.rs` `//!`
- **Generated artifact:** the marked region of `README.md`
- **CI gate:** `cargo rdme --check` fails if the marked region drifts from the `//!` block

This is the opposite direction of `#![doc = include_str!("../README.md")]`, which pulls README content into `lib.rs`. Crates that currently use `include_str!` must be migrated; see [Migration](#migration-from-include_str).

cargo-rdme automatically:

- strips `# `-prefixed hidden lines from doctests when injecting into README
- tags rust code blocks with `rust` for syntax highlighting
- rewrites `[Type](crate::Type)` intra-doc links to `https://docs.rs/<crate>/latest/...` URLs in the README
- bumps heading levels in injected content based on the README's surrounding heading level

These transforms make a single `//!` block render correctly on both docs.rs and GitHub.

## Scope

In scope:

- adopting cargo-rdme on a new or existing crate
- migrating off `#![doc = include_str!("../README.md")]` (or `cfg_attr` variants)
- restructuring `src/lib.rs` `//!` and `README.md` to the standard layout
- adding `<!-- cargo-rdme -->` markers, `.cargo-rdme.toml`, CI step, justfile recipes
- verifying the resulting docs.rs page, doctests, and README diff

Out of scope:

- writing the substantive docs content (defer to `crate-docs-update`)
- commit messages for the migration (defer to `changelog-commit-message`)
- reviewing `///` doc structure on individual public items (defer to `rust-api-docs`)
- Cargo.toml / feature flag / MSRV / lint review (defer to `rust-cargo-hygiene`)
- crates that already use cargo-rdme correctly and only need content edits (defer to `crate-docs-update`)

## Prerequisites

- a published or to-be-published Rust library crate with `src/lib.rs`
- a `README.md` declared via `Cargo.toml`'s `readme = "README.md"` (or default)
- `cargo install --locked cargo-rdme` available locally (CI installs it on demand)
- ability to run `cargo doc --no-deps` and `cargo test --doc` for the crate

## Workflow

### 1. Inspect current state

Read every file the migration touches before editing anything.

- `README.md` (full file): note the badge block, the API-relevant prose/example, repo-relative links to `docs/*.md`, install/MSRV/contributing/license sections, and any GitHub-only markdown (collapsible `<details>`, alerts, relative image paths)
- `src/lib.rs` (top of file): note crate attributes (`#![forbid(unsafe_code)]`, `#![warn(missing_docs)]`, lints), any `#![doc = include_str!(...)]` or `cfg_attr` doc-include, and the existing `//!` block
- `Cargo.toml`: confirm `readme` field; note `[package.metadata.docs.rs]` config (features, all-features, rustdoc args)
- `.cargo-rdme.toml` (if it exists): existing configuration
- `.github/workflows/ci.yml` (or equivalent): identify where to insert the cargo-rdme step
- `justfile` (if present): identify the `_ensure-*` helpers, the `check`/`fix`/`ci` aggregators, and the surrounding recipe style

### 2. Plan content placement

Decide what belongs in `//!` (the docs.rs landing page) versus elsewhere in the README. Use this rubric:

Goes in `lib.rs` `//!` (visible on docs.rs *and* in README):

- one-paragraph elevator pitch
- minimal working example (must compile as a doctest)
- brief feature/concepts overview
- pointers to deeper crate items via intra-doc links such as `[Thing](crate::Thing)`
- audience / when-to-use / when-not-to-use, if short
- validation/safety/contract pointers, if short

Stays only in README (outside markers):

- badges (CI, crates.io, docs.rs, codecov, DOI, license)
- `cargo add <crate>` install snippet
- MSRV statement
- Cargo features table
- project status / pre-release warnings
- roadmap / TODO / known issues
- detailed examples that need external setup or shell scripts
- contributing / Code of Conduct / Security / License sections
- repo-relative links to `docs/*.md`, `examples/`, `benches/`, `CHANGELOG.md`
- GitHub-only markdown (collapsible blocks, alerts, relative images)

The `//!` block targets API readers on docs.rs. Marketing, install instructions, governance, and repo-internal links belong outside the markers.

### 3. Restructure `src/lib.rs` `//!`

Apply the [standard lib.rs template](#standard-libsrs-template). Key constraints:

- keep crate attributes (`#![forbid(unsafe_code)]`, lint configuration, `#![cfg_attr(docsrs, feature(doc_cfg))]`) above the `//!` block
- the `//!` block is one contiguous block immediately after the crate attributes
- every code block in `//!` must be a valid doctest against the public API; mark non-runnable examples with the `rust,no_run`, `rust,ignore`, or `text` fence info-strings as appropriate
- prefer the intra-doc-link form `[Thing](crate::Thing)` over bare backticked names so cargo-rdme can rewrite the link to docs.rs in the README; reference-style links work too
- use hidden setup lines (`# use crate::...;`) inside doctests freely — cargo-rdme strips them from the README
- avoid headings deeper than `#` and `##` inside `//!`; cargo-rdme will bump them based on the README's surrounding heading level

If the crate currently has additional hand-written `//!` content beyond what the README needs (e.g. delaunay-style "validation hierarchy" contract docs), keep that content **inside** the same `//!` block — it will appear on both surfaces, which is usually correct since GitHub readers also benefit from it. If you genuinely want content on docs.rs only, move it into a module-level `//!` (e.g. `src/contract.rs` with `//!` docs and `pub mod contract;`).

### 4. Restructure `README.md`

Apply the [standard README template](#standard-readme-template). Key constraints:

- badges block sits at the top, before any heading or the marker
- a single `<!-- cargo-rdme -->` marker (no `start`/`end` yet — cargo-rdme inserts those on first run) marks where the `//!` block will be injected
- everything below the marker is GitHub-only content (install, MSRV, features, examples that need external setup, roadmap, contributing, license)
- remove any content from the README that now lives in `//!` — duplicating it defeats the purpose and risks drift between editing rounds
- repo-relative links (`./docs/workflows.md`, `./CHANGELOG.md`) belong outside the marker because they break on docs.rs

### 5. Run cargo-rdme to populate the README

```bash
cargo install --locked cargo-rdme
cargo rdme
```

cargo-rdme replaces the `<!-- cargo-rdme -->` marker with `<!-- cargo-rdme start -->` / `<!-- cargo-rdme end -->` bracketing the injected `//!` content. Subsequent runs update the content between those markers.

Inspect the resulting README diff:

- intra-doc links resolved to `https://docs.rs/<crate>/latest/...`
- code blocks tagged `rust` and hidden lines stripped
- heading levels bumped to nest under the surrounding README heading (often none, since the marker typically sits at the top level)
- no unintended content loss outside the markers

### 6. Add `.cargo-rdme.toml` if defaults are insufficient

Defaults work for most library crates. Add `.cargo-rdme.toml` only when you need:

- non-default README path (e.g. workspace member with a custom README)
- explicit `heading-base-level` to control nesting
- `[entrypoint] type = "bin"` for binary crates
- pinned `[intralinks] docs-rs-version = "X.Y.Z"` instead of `latest`

See [.cargo-rdme.toml example](#cargo-rdmetoml-example).

### 7. Wire CI

Add a step to the existing CI workflow (typically `.github/workflows/ci.yml`). See [GitHub Actions snippet](#github-actions-snippet). Place it after the checkout/toolchain setup and alongside other doc-related checks (e.g., `cargo doc --no-deps`).

cargo-rdme exit codes:

- `0` — README is up to date
- `3` — README does not match the documentation (i.e. drift)
- `4` — warnings emitted (e.g. unresolved intralinks)

### 8. Wire the justfile

If the repo uses a justfile, add:

- a `_ensure-cargo-rdme` helper consistent with existing `_ensure-*` recipes
- a `docs-readme` recipe (mutating, runs `cargo rdme`) — add to the `fix` aggregator
- a `docs-readme-check` recipe (non-mutating, runs `cargo rdme --check`) — add to the `check` and `ci` aggregators

See [justfile snippet](#justfile-snippet).

### 9. Validate

Run all of the following and confirm clean exits:

- `cargo doc --no-deps` — confirms `//!` renders without rustdoc errors
- `cargo test --doc` — confirms every doctest in `//!` compiles and passes
- `cargo rdme --check` — confirms the README's marked region matches `//!`
- visual inspection of the rendered docs.rs preview locally via `cargo doc --open`
- visual inspection of `README.md` on GitHub (push to a branch and view the diff)

If `[package.metadata.docs.rs]` enables features that gate items in `//!`, verify those examples still compile with the gated features off.

## Standard lib.rs template

````rust path=null start=null
//! One-paragraph elevator pitch describing what the crate does and the
//! problem it solves. Name the audience and the core abstraction. Keep
//! to ~3 sentences.
//!
//! # Quick start
//!
//! ```
//! use crate_name::prelude::*;
//!
//! let thing = Thing::new();
//! assert_eq!(thing.value(), 42);
//! ```
//!
//! # Concepts
//!
//! Brief tour of the main types and how they fit together. Link to
//! deeper items with intra-doc links so the README points at docs.rs:
//! [`Thing`](crate::Thing), [`module`](crate::module).
//!
//! # When to use this crate
//!
//! - bullet describing a fit
//! - bullet describing another fit
//!
//! # When *not* to use this crate
//!
//! - bullet describing a non-fit (links to alternatives)

#![forbid(unsafe_code)]
#![warn(missing_docs)]
#![deny(rustdoc::broken_intra_doc_links)]
#![cfg_attr(docsrs, feature(doc_cfg))]
````

If the crate already has long-form contract docs (e.g. validation hierarchy, invariants stack), keep them inside the same `//!` block under additional `# `-level headings, or move them into a module with its own `//!`. Prefer to keep the front-page short — readers who need contract depth will click through.

Crate attributes (`#![forbid(...)]`, `#![warn(...)]`, etc.) go *after* the `//!` block in the file's source order; `//!` must come first to be the crate-level doc. The placement above is a convention; either order works as long as `//!` is the first inner doc comment in the file.

## Standard README template

````markdown path=null start=null
# crate-name

[![Crates.io](https://img.shields.io/crates/v/crate-name.svg)](https://crates.io/crates/crate-name)
[![Downloads](https://img.shields.io/crates/d/crate-name.svg)](https://crates.io/crates/crate-name)
[![Docs.rs](https://docs.rs/crate-name/badge.svg)](https://docs.rs/crate-name)
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/<owner>/<repo>/graph/badge.svg)](https://codecov.io/gh/<owner>/<repo>)
[![License](https://img.shields.io/crates/l/crate-name.svg)](./LICENSE)

<!-- cargo-rdme -->

## Installation

```sh
cargo add crate-name
```

## Minimum Supported Rust Version

Rust 1.XX or newer.

## Cargo features

- `default` — ...
- `serde` — enable serde support for ...

## Project status

🚧 Pre-release / Stable / Maintenance — short status sentence.

## Examples

See [`examples/`](./examples/) and [`docs/workflows.md`](./docs/workflows.md) for end-to-end recipes that need external setup beyond a single doctest.

## Roadmap

- [x] item
- [ ] item

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md), [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md), and [SECURITY.md](./SECURITY.md).

## License

Dual-licensed under [MIT](./LICENSE-MIT) or [Apache-2.0](./LICENSE-APACHE) at your option.
````

After the first `cargo rdme` run, the marker line becomes a marker pair with the injected `//!` content between them. Treat the content between the markers as generated; never hand-edit it. Hand-edit `//!` and re-run `cargo rdme`.

## .cargo-rdme.toml example

Only commit this if defaults are insufficient.

```toml path=null start=null
# Override the README path; defaults to Cargo.toml's `readme` field.
# readme-path = "README.md"

# Pin line endings; defaults to inferring from the file.
line-terminator = "lf"

# Pin the docs.rs version used in injected intralinks. Default is "latest".
# Pinning is rarely worth it; "latest" tracks new releases automatically.
# [intralinks]
# docs-rs-version = "0.5.0"

# For binary-only crates, point cargo-rdme at main.rs instead of lib.rs.
# [entrypoint]
# type = "bin"
# bin-name = "my-bin"
```

## GitHub Actions snippet

Add to `.github/workflows/ci.yml` (or the workflow that already runs `cargo doc` / `cargo test --doc`). Place after toolchain setup and Rust caching, alongside other doc checks.

```yaml path=null start=null
- name: Install cargo-rdme
  uses: taiki-e/install-action@v2
  with:
    tool: cargo-rdme

- name: Verify README is in sync with lib.rs
  run: cargo rdme --check
```

If the repo does not use `taiki-e/install-action`, fall back to:

```yaml path=null start=null
- name: Verify README is in sync with lib.rs
  run: |
    cargo install --locked cargo-rdme
    cargo rdme --check
```

`cargo rdme --check` exits `3` on drift and `4` on warnings; the workflow fails on either.

## justfile snippet

Match the style of existing `_ensure-*` and aggregator recipes. Insert in the appropriate alphabetical/section position.

```make path=null start=null
_ensure-cargo-rdme:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! cargo rdme --version >/dev/null 2>&1; then
        echo "❌ 'cargo-rdme' not found. Install with:"
        echo "   cargo install --locked cargo-rdme"
        exit 1
    fi

# Regenerate README.md API section from src/lib.rs //! (mutating).
docs-readme: _ensure-cargo-rdme
    cargo rdme

# Verify README.md API section matches src/lib.rs //! (non-mutating).
docs-readme-check: _ensure-cargo-rdme
    cargo rdme --check
```

Add `docs-readme-check` to the existing `check` and `ci` aggregator recipes, and `docs-readme` to the existing `fix` aggregator. Keep the additions adjacent to other doc-related steps if any (`cargo doc`, `cargo test --doc`).

If the repo's `setup` recipe prints a checklist of external tooling, add `cargo-rdme` to that checklist.

## Migration from `include_str!`

Crates that currently embed the README into `lib.rs` need a structural change. Typical starting state:

```rust path=null start=null
#![doc = include_str!("../README.md")]
// or:
#![cfg_attr(any(doc, doctest), doc = include_str!("../README.md"))]

//! ...optional additional contract docs...
```

Migration steps:

1. **Capture current API content.** Read the README's introduction, minimal example, concepts, and any other API-facing prose. This is what will move into `//!`.
2. **Delete the doc-include attribute.** Remove `#![doc = include_str!("../README.md")]` (and any `cfg_attr` wrapper). The crate-level docs will come from `//!` directly.
3. **Move API content into `//!`.** Place it at the top of `lib.rs` before any crate attributes that depend on doc resolution. If there was already a hand-written `//!` block (e.g. delaunay's "Documentation map" / "Triangulation invariants" sections), merge: README-derived content first, then the existing contract docs, all in one `//!` block.
4. **Strip the old API content from the README.** Anything now in `//!` should be removed from the README's body. Add a single `<!-- cargo-rdme -->` marker where the API section used to be. Keep badges above the marker; keep install/MSRV/contributing/license below.
5. **Convert any bare backticked type names to intra-doc links** in the form `[Thing](crate::Thing)` in the migrated `//!` content so the README links to docs.rs.
6. **Run `cargo rdme`** to populate the marked region.
7. **Compare diffs.**
   - The README diff should remove the old hand-written API prose and add the `<!-- cargo-rdme start -->` ... `<!-- cargo-rdme end -->` block with the injected content.
   - The `lib.rs` diff should remove the doc-include attribute and add (or extend) the `//!` block.
8. **Run validation:** `cargo doc --no-deps`, `cargo test --doc`, `cargo rdme --check`.

Common gotchas:

- **Doctest examples that referenced README-only context.** Hidden setup lines must use `# `-prefixed doctest syntax inside `//!` (not raw markdown comments).
- **Badge block survival.** The badge block must stay above the marker; cargo-rdme leaves content outside markers untouched.
- **Heading collisions.** If `//!` uses `# Foo` and the README places the marker under a `## Section`, cargo-rdme bumps the injected headings. Use `--heading-base-level` or restructure if the result looks off.
- **Repo-relative links inside `//!`.** Links like `./docs/workflows.md` resolve on GitHub (after cargo-rdme injects them) but break on docs.rs. Either move those links outside the marker (so they only appear in the README), or convert them to absolute `https://github.com/<owner>/<repo>/blob/main/docs/workflows.md` URLs.
- **`[package.metadata.docs.rs]` features.** If `//!` examples depend on default-off features, ensure docs.rs metadata enables them so the rendered page compiles.

## Per-crate convention sensitivity

Read the existing repo before adopting standard layouts wholesale.

- some crates already have a `prelude` module; the `//!` quick-start example should use it (`use crate_name::prelude::*;`)
- some crates ship multiple scoped preludes (e.g. delaunay's `prelude::triangulation`, `prelude::geometry`); pick the smallest one that supports the example
- if the crate has long-running contract docs (validation hierarchy, invariants stack), preserve them — don't trim contract docs to fit a "minimal landing page" ideal
- match the badge set used by sibling crates in the same ecosystem (consistency across crates is a goal of this skill)

## Output Format

### Pre-migration state inspected

- README.md: section list, badge count, existing API content location
- src/lib.rs: crate attributes, presence of `include_str!` doc attribute, existing `//!` block contents
- Cargo.toml: `readme` field, `[package.metadata.docs.rs]` config
- CI workflow file and the insertion point for the cargo-rdme step
- justfile recipes touched (if applicable)

### Plan

- content moving from README → `lib.rs` `//!`
- content staying in README outside markers
- attribute removals (`include_str!`, `cfg_attr`)
- new files (`.cargo-rdme.toml`, if any)
- CI / justfile additions

### Changes made

- `src/lib.rs`: attributes removed, `//!` block written/extended
- `README.md`: API content removed, marker inserted, badges/install/etc. preserved
- `.cargo-rdme.toml`: created (or skipped, with reason)
- CI workflow: cargo-rdme install + check step added at <line>
- justfile: `_ensure-cargo-rdme`, `docs-readme`, `docs-readme-check` added; aggregator recipes updated

### Validation

- `cargo doc --no-deps` — pass / fail (with diagnostics)
- `cargo test --doc` — pass / fail (with diagnostics)
- `cargo rdme --check` — pass / fail (with diff if drift)
- local docs.rs preview spot-check (intralinks resolve, code blocks render)

### Follow-ups

- doc gaps deliberately not filled in this migration (defer to `crate-docs-update`)
- `///` improvements to public items (defer to `rust-api-docs`)
- Cargo.toml lint / feature changes that surfaced (defer to `rust-cargo-hygiene`)
- next crates in the standardization sweep
