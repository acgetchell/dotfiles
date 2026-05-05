---
name: cargo-rdme-adoption
description: "Standardize a Rust crate's docs.rs API guide and README using cargo-rdme, treating src/lib.rs //! as the single source of truth for the generated README API section while the hand-written README owns the GitHub landing page. USE FOR: adopting cargo-rdme on a new or existing crate; producing a uniform docs.rs API guide across multiple crates; migrating away from #![doc = include_str!(\"../README.md\")] / #![cfg_attr(any(doc, doctest), doc = include_str!(\"../README.md\"))]; restructuring src/lib.rs //! as the generated technical API guide; reformatting README.md to the standard layout (badges → hand-written GitHub landing page → cargo-rdme API guide marker → examples/docs/contributing/citation); adding cargo rdme --check to CI; adding docs-readme/docs-readme-check recipes to a justfile; producing a .cargo-rdme.toml when defaults are not enough. DO NOT USE FOR: writing substantive doc content (use crate-docs-update); commit messages (use changelog-commit-message); reviewing /// public-API doc sections (use rust-api-docs); Cargo.toml / feature flag / MSRV review (use rust-cargo-hygiene); non-Rust repositories; repositories that already correctly use cargo-rdme and only need content edits."
---

# cargo-rdme-adoption

Adopt cargo-rdme on a Rust crate so the **`src/lib.rs` `//!` block is the single source of truth for the generated API guide** on docs.rs and in the README, kept in sync by a CI gate. The hand-written README remains the GitHub landing page.

This skill is about the mechanism (markers, `lib.rs` ↔ README sync, CI wiring) and the canonical layout. It is not about writing the substantive prose; for that, defer to `crate-docs-update`.

## The cargo-rdme model

cargo-rdme reads the crate-level `//!` doc comment from `src/lib.rs` and injects it into the README between cargo-rdme markers. The flow is:

- **Source of truth:** `src/lib.rs` `//!` for the generated API guide
- **Generated artifact:** the marked API-guide region of `README.md`
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

Decide what belongs in `//!` (the docs.rs API guide and generated README API section) versus elsewhere in the README. Use this rubric:

Goes in `lib.rs` `//!` (visible on docs.rs *and* in the README API guide):

- concise API-guide opening that explains what the generated section covers
- minimal working examples that must compile as doctests
- technical concepts and API relationships
- pointers to deeper crate items via intra-doc links such as `[Thing](crate::Thing)`
- **scientific basis / scope / contract sections**, even when long: acceptance formulae, MCMC/Metropolis-Hastings contract bullets, log-space conventions, "what the crate provides" / "what the crate does not prove", invariants stack, validation hierarchy, numerical-semantics notes, safety/contract pointers — these describe the API contract and belong on docs.rs alongside the API they shape

Stays only in README (outside markers):

- badges (CI, crates.io, docs.rs, codecov, DOI, license)
- short hand-written GitHub landing page before the cargo-rdme marker: one-paragraph pitch, status/pre-release note, install snippet, MSRV, Cargo feature flags, minimal quick start, and a "which API should I choose?" guide
- audience / "Use this crate when you want" bullets and broad capability overview, kept concise
- `cargo add <crate>` install snippet
- MSRV statement
- Cargo features table
- project status / pre-release warnings
- roadmap / TODO / known issues
- detailed examples that need external setup or shell scripts
- contributing / Code of Conduct / Security / License sections
- repo-relative links to `docs/*.md`, `examples/`, `benches/`, `CHANGELOG.md`
- GitHub-only markdown (collapsible blocks, alerts, relative images)

The `//!` block targets API readers on docs.rs and becomes the README's detailed API guide. The README still needs a GitHub landing page before that generated block so new users can install, see status, understand when to use the crate, run a minimal example, and pick the right API without scrolling through long-form contract documentation. Governance and repo-internal links belong outside the markers.

### 3. Restructure `src/lib.rs` `//!`

Apply the [standard lib.rs template](#standard-libsrs-template). Key constraints:

- keep crate attributes (`#![forbid(unsafe_code)]`, lint configuration, `#![cfg_attr(docsrs, feature(doc_cfg))]`) above the `//!` block
- the `//!` block is one contiguous block immediately after the crate attributes
- every code block in `//!` must be a valid doctest against the public API; mark non-runnable examples with the `rust,no_run`, `rust,ignore`, or `text` fence info-strings as appropriate
- prefer the intra-doc-link form `[Thing](crate::Thing)` over bare backticked names so cargo-rdme can rewrite the link to docs.rs in the README; reference-style links work too
- use hidden setup lines (`# use crate::...;`) inside doctests freely — cargo-rdme strips them from the README
- avoid headings deeper than `#` and `##` inside `//!`; cargo-rdme will bump them based on the README's surrounding heading level
- **keep the generated API guide scannable but do not duplicate the README landing page.** The top of `//!` should say what the API guide covers, state the core API contract, and then move into deeper sections such as `# Scientific basis and scope`, `# Numerical semantics`, validation hierarchy, invariants stack, and worked examples. Do not copy the README's pre-release banner, "Use this crate when you want" bullets, or broad feature/capability list into `//!` unless the repository has no hand-written landing page. If both surfaces need similar facts, keep the README version short and user-facing, and make the `//!` version technical and contract-focused.

If the crate currently has additional hand-written `//!` content beyond what the README needs (e.g. delaunay-style "validation hierarchy" contract docs), keep that content **inside** the same `//!` block — it will appear on both surfaces, which is usually correct since GitHub readers also benefit from it. If you genuinely want content on docs.rs only, move it into a module-level `//!` (e.g. `src/contract.rs` with `//!` docs and `pub mod contract;`).

### 4. Restructure `README.md`

Apply the [standard README template](#standard-readme-template). Key constraints:

- badges block sits at the top, before any landing prose or marker
- the README should lead like a hand-written GitHub landing page (matching sibling crates such as delaunay when applicable): short pitch, project status, install snippet, MSRV, Cargo features, minimal quick-start example, and a compact API-choice guide
- a single `<!-- cargo-rdme -->` marker (no `start`/`end` yet — cargo-rdme inserts those on first run) marks where the `//!` block will be injected as the detailed API guide
- everything below the marker is GitHub-only content that remains useful after the detailed API guide: examples directory links, documentation map, ecosystem, contributing, citation, references, license
- remove long API-guide content from the README that now lives in `//!`, but keep a concise hand-written landing page before the marker. Do not move the entire pitch/status/use-case/feature overview into `//!` just because cargo-rdme can generate it.
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

### 10. Document the generation

Future editors (human and agent) need to know that the README's marker region is generated. Add documentation in three places so this is hard to miss:

- **Inline in `README.md`**, immediately above the cargo-rdme markers — a short HTML comment that explains the region is generated and points at the regenerate command. This is the most local hint and survives even if other docs are skipped.

  ```markdown path=null start=null
  <!-- The block between the cargo-rdme markers below is generated from src/lib.rs //!.
       Do not edit it by hand. To update: edit src/lib.rs and run `just docs-readme`. -->
  <!-- dprint-ignore-start -->
  <!-- cargo-rdme start -->
  ```

- **`AGENTS.md`** (or equivalent agent-instruction file): add a `## Documentation generation` section that names cargo-rdme as the generator, defines the marker block, lists the rules (never hand-edit the region; edit `//!` and regenerate; CI runs `cargo rdme --check`), explains why `<!-- dprint-ignore-* -->` markers are present if applicable, and clarifies that outside-markers content is hand-written. Place it adjacent to the existing `## Publishing note` / `## Editing tools policy` sections so doc-related guidance lives together. Also amend the `## Publishing note` section to remind users to run `just docs-readme` before tagging a release.

- **`CONTRIBUTING.md`** (if the repo has one): mirror the `AGENTS.md` rules in shorter form so human contributors see the same guidance during a normal PR flow.

If the repo's `justfile` `help-workflows` or `setup` recipes print a guide, add a one-line mention of `just docs-readme` / `just docs-readme-check` there too.

### 11. Duplication audit

After cargo-rdme has populated the README, scan for facts that now appear both inside the cargo-rdme markers (generated from `//!`) and outside them (hand-written README content). The README is allowed to have a **short hand-written landing summary** before the generated block, but it should not carry long verbatim copies of the same API sections. The goal is: concise orientation before the generated API guide; detailed content in `//!`.

A quick mechanical check: extract the outside-markers content and grep it for keywords that appear in `//!`.

```bash
awk '/<!-- cargo-rdme end -->/{out=1; next} out{print}' README.md \
  | grep -nE 'Pre-release|Quickstart|Use this crate|Features|Scientific|Numerical'
```

Common duplicate patterns to look for and either shorten or remove:

- pre-release / status banners (keep at most a one-line landing banner outside the markers)
- audience or "Use this crate when you want" bullets (keep a shorter landing list if useful; do not duplicate the full generated list verbatim)
- feature / capability lists (outside markers should be Cargo feature flags or a short user-facing summary, not a second long capability list)
- minimal-example code blocks (`//!` carries a runnable doctest; the README may keep a compact common-path quick start, but should not repeat every generated worked example)
- "What the crate provides" / "What the crate does not prove" framing
- repeated CITATION / REFERENCES sentences when those already have dedicated sections lower in the README
- `cargo add <crate>` snippets that double as both Quickstart leadin and Installation
- Scientific-basis or contract paragraphs that lingered in the README after their content moved into `//!`

**Rule of thumb:** if a long API fact appears twice in the rendered README, delete or shorten the version OUTSIDE the markers — `//!` is the source of truth for the generated API guide. If the outside-markers text is a concise landing summary that helps a new GitHub reader orient quickly (pitch, status, install, quick start, API-choice guide), keep it short and link/scroll to the generated API guide for depth. If a section feels valuable on docs.rs but currently only lives outside the markers, move it INTO `//!` instead of duplicating it.

Sections that legitimately stay outside the markers — even if they share keywords with `//!` — are those that serve a different audience or purpose and would be noise or too package-manager/repo-specific on docs.rs:

- hand-written landing pitch / status / quick start / API-choice guide before the marker — concise GitHub orientation, distinct from long-form generated API docs
- `## Installation` or quick-start `cargo add` snippets — package-manager flavored, addresses installers rather than API readers
- `## Minimum Supported Rust Version` or brief MSRV sentence
- `## Cargo features` table/list — explicit feature names with how to enable; distinct from `//!` capability bullets that just note the feature exists
- `## Examples` directory listing with `examples/foo.rs` repo links — distinct from `//!` doctests, which are inline and runnable
- `## Documentation` — repo-internal `docs/*.md` and `CHANGELOG.md` links that wouldn't resolve on docs.rs
- `## Ecosystem`, `## Contributing`, `## Citation`, `## References`, `## AI Agents`, license sections

When you delete an outside-markers section to remove a duplicate, preserve any unique links it carried by folding them into a section that stays — most often `## Documentation`. For example, removing a `## Project status` section that duplicated the pre-release banner is fine, but keep the `CHANGELOG.md` link by adding it to `## Documentation`.

Finally: outside-markers sections should themselves be **short and punchy**. Their job is to orient readers and point them at the right place, not to repeat the long-form content already in `//!`. A few sentences, a compact quick-start example, and a link list per section is usually enough.

## Standard lib.rs template

````rust path=null start=null
//! Generated API guide for crate-name.
//!
//! This section documents the crate's public API contracts, core concepts,
//! examples, and operational semantics. For installation, crate status,
//! feature flags, and API-selection guidance, see the hand-written README
//! sections before the cargo-rdme marker.
//!
//! # Core contract
//!
//! Describe the central trait/type contract that API users must honor.
//! Keep this technical and link public items with intra-doc links such as
//! [`Thing`](crate::Thing).
//!
//! # Example
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

#![forbid(unsafe_code)]
#![warn(missing_docs)]
#![deny(rustdoc::broken_intra_doc_links)]
#![cfg_attr(docsrs, feature(doc_cfg))]
````

If the crate already has long-form contract docs (e.g. validation hierarchy, invariants stack), keep them inside the same `//!` block under additional `# `-level headings, or move them into a module with its own `//!`. Prefer to keep the generated API guide's opening short — readers who need contract depth will scroll.

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

Short hand-written pitch for GitHub readers.

🚧 **Pre-release (0.x)** — Short status sentence, if applicable.

Use this crate when you want:

- concise user-facing fit
- concise capability summary
- concise production/validation note

## 🚀 Quick start

```sh
cargo add crate-name
```

Rust 1.XX or newer.

Minimal example focused on the common path.

## 🧭 Choosing an API

- Start with the simplest API for the common path.
- Escalate to specialized APIs when the user's state or workflow needs them.

## 📦 Cargo features

- `default` — ...
- `serde` — enable serde support for ...

## 📚 API guide

<!-- The block between the cargo-rdme markers below is generated from src/lib.rs //!.
     Do not edit it by hand. To update: edit src/lib.rs and run `just docs-readme`. -->
<!-- cargo-rdme -->

## 🧪 Examples

See [`examples/`](./examples/) and [`docs/workflows.md`](./docs/workflows.md) for end-to-end recipes that need external setup beyond a single doctest.

## 🗺️ Roadmap

- [x] item
- [ ] item

## 🤝 Contributing

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
- **Unresolvable intra-doc links via re-exports.** cargo-rdme's heuristic intralink resolver does NOT follow `pub use private_mod::Type` re-exports. If your crate root re-exports types from private modules (e.g. `mod traits;` + `pub use traits::Target;`), `[Target](crate::Target)` will emit `warning: Could not resolve definition of crate::Target` and `cargo rdme --check` will exit `4` (warnings). Three workarounds, in order of preference: (a) drop the `(crate::Type)` form for that specific link and use plain backticks (`` `Target<S>` ``); the rustdoc-shortcut form `[`Type`]` elsewhere in `//!` still resolves natively on docs.rs, (b) use an absolute docs.rs URL (`[`Target`](https://docs.rs/<crate>/latest/<crate>/trait.Target.html)`), or (c) make the underlying module `pub mod` so the path is reachable. Run `cargo rdme` once after writing `//!` to see which links fail to resolve, then patch them. The lib.rs intra-doc links remain valid for native rustdoc rendering on docs.rs even when cargo-rdme can't render them in the README.
- **`cargo rdme` refuses to overwrite a dirty README.** First run after inserting the marker exits with `error: not updating README: it has uncommitted changes (use --force to bypass this check)`. This is intentional. Pass `--force` to seed the marker region the first time. After that, ordinary `cargo rdme` runs work without `--force` against a clean tree.
- **dprint markdown formatter conflicts with cargo-rdme's preserved line wrapping.** If the repo formats markdown with `dprint` (`dprint.json` with the markdown plugin) and `markdown.textWrap` is set to `"never"` or `"always"`, dprint will rewrap the cargo-rdme region and `cargo rdme --check` will then see drift. Fix by wrapping the cargo-rdme region with `<!-- dprint-ignore-start -->` / `<!-- dprint-ignore-end -->` markers placed around (not inside) the cargo-rdme markers, e.g.:

  ```text
  <!-- dprint-ignore-start -->
  <!-- cargo-rdme start -->
  ...generated content...
  <!-- cargo-rdme end -->
  <!-- dprint-ignore-end -->
  ```

  cargo-rdme leaves both dprint comments alone (they sit outside its own markers); dprint sees its ignore region and skips formatting. The same problem affects `prettier` (`<!-- prettier-ignore-start -->` / `<!-- prettier-ignore-end -->`), `markdownlint` (`<!-- markdownlint-disable --> ... <!-- markdownlint-enable -->`), and other markdown formatters with similar disable directives. Inspect the repo's markdown tooling before running `cargo rdme` for the first time and add the appropriate ignore markers as part of the migration.

## Per-crate convention sensitivity

Read the existing repo before adopting standard layouts wholesale.

- some crates already have a `prelude` module; the `//!` quick-start example should use it (`use crate_name::prelude::*;`)
- some crates ship multiple scoped preludes (e.g. delaunay's `prelude::triangulation`, `prelude::geometry`); pick the smallest one that supports the example
- if the crate has long-running contract docs (validation hierarchy, invariants stack), preserve them — don't trim contract docs to fit a "minimal landing page" ideal
- **API contract sections in the README belong in `lib.rs` `//!`, not outside the markers.** If the README has a "Scientific basis", "Scope", "Contract", "What the crate provides", "What the crate does not prove", "Numerical semantics", "Validation and guarantees", or similar section that describes how the public API is meant to be used (acceptance rules, log-space conventions, what's proven vs. caller's responsibility), move it INTO `//!` during the migration. These sections are docs.rs-relevant even when long — leaving them outside the markers means docs.rs readers miss the contract that shapes correct API use. Convert any repo-relative links in the moved content (`./docs/foo.md`) to absolute GitHub URLs so they still resolve on docs.rs.
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
- `README.md`: hand-written GitHub landing page added/preserved before the marker, generated API marker inserted, duplicate long-form API content removed outside the markers, inline HTML comment added above the markers
- `.cargo-rdme.toml`: created (or skipped, with reason)
- CI workflow: cargo-rdme install + check step added at <line>
- justfile: `_ensure-cargo-rdme`, `docs-readme`, `docs-readme-check` added; aggregator recipes updated
- `AGENTS.md` / `CONTRIBUTING.md`: `## Documentation generation` section added explaining the cargo-rdme flow; `## Publishing note` (if present) updated to mention `just docs-readme` before release

### Validation

- `cargo doc --no-deps` — pass / fail (with diagnostics)
- `cargo test --doc` — pass / fail (with diagnostics)
- `cargo rdme --check` — pass / fail (with diff if drift)
- local docs.rs preview spot-check (intralinks resolve, code blocks render)

### Duplication audit

- duplicates found between marker region and outside-markers content (list each with line numbers)
- which outside-markers content was shortened or deleted and where any unique links from a removed section were re-homed (typically `## Documentation`)
- outside-markers sections kept as legitimate non-duplicates or concise landing summaries (pitch/status/install/MSRV/Cargo features/quick start/API-choice guide, Examples directory, Documentation, Ecosystem, Contributing, Citation, References, License)
- confirmation that `//!` opens as a technical API guide and does not duplicate the README's pitch/status/use-case/feature overview

### Follow-ups

- doc gaps deliberately not filled in this migration (defer to `crate-docs-update`)
- `///` improvements to public items (defer to `rust-api-docs`)
- Cargo.toml lint / feature changes that surfaced (defer to `rust-cargo-hygiene`)
- next crates in the standardization sweep
