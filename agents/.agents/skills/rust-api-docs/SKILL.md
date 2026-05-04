---
name: rust-api-docs
description: "Audit Rust public API documentation for required sections, intra-doc links, and crate-level docs. USE FOR: doc comment structure on public API, # Errors / # Panics / # Safety / # Examples sections, intra-doc links, crate-level //! overviews, module-level docs, missing or weak descriptions, deny(missing_docs) and broken_intra_doc_links lint configuration, semver-relevant doc updates, docs.rs feature visibility. DO NOT USE FOR: doctest test quality (use rust-test-quality), private helper /// docs (use rust-test-quality), error variant design (use rust-error-variants), trait bound docs (use rust-trait-bounds), non-Rust code, or unchanged APIs."
---

# rust-api-docs

Audit Rust public API documentation for completeness, structure, and discoverability.

Good public docs explain why callers would use the item, what they must guarantee, and what to expect when things go wrong. They also enable `cargo doc` and docs.rs to render the public surface coherently.

## Scope

Focus on newly added or modified public Rust APIs that:

- expose new functions, methods, types, traits, or modules
- change behavior, error contracts, panic conditions, or safety invariants
- introduce features gated by `cfg` flags
- produce items intended to appear in published `cargo doc`

Ignore private items unless reviewing them surfaces a public API documentation gap.

## Review goals

### 1. Required structured sections

Check that public items use the conventional doc sections when they apply:

- `# Errors` for any function returning `Result`, naming the conditions for each error variant
- `# Panics` for any function that may panic on documented preconditions
- `# Safety` for `unsafe fn` and unsafe traits, naming the invariants callers must uphold
- `# Examples` for non-trivial public items, with at least one runnable doctest

Flag:

- missing `# Errors` for fallible APIs
- missing `# Panics` when panics are reachable from valid inputs
- missing `# Safety` on unsafe items
- missing `# Examples` on items meant to be discoverable
- empty section bodies left as headings only

### 2. Description quality

Check that doc comments:

- start with a one-line summary that names the operation and its result
- explain why the item exists, not only what it does
- describe pre/post-conditions when they matter
- mention complexity when it is non-obvious or part of the contract
- describe the unit, range, or shape of inputs and outputs

Flag:

- summaries that only restate the item name
- empty doc comments left as `///` placeholders
- documentation that contradicts the implementation
- descriptions that document an internal helper rather than the public contract

### 3. Intra-doc links

Check that references to other items use intra-doc links (`[Type]`, `` [`Type::method`] ``, `` [`crate::module::Item`] ``).

Flag:

- bare type names that should be linked
- broken intra-doc links
- raw URLs to docs.rs when an intra-doc link is available
- linkified prose that obscures readability with backticks where plain words would do

### 4. Crate- and module-level docs

Check:

- `lib.rs` (or `main.rs`) has a top-level `//!` overview describing what the crate is for, when to use it, and how the prelude/feature flags work
- public modules have `//!` docs that orient the reader
- feature-gated items document the required feature with `#[doc(cfg(feature = "..."))]` or equivalent prose
- items intended for a particular audience (testing, internal compatibility, examples) say so

Flag:

- missing crate-level docs on a published library
- modules whose purpose is unclear from the docs
- feature-gated APIs whose feature requirement is invisible in the rendered docs

### 5. Lints and configuration

Check:

- `#![deny(missing_docs)]` or `#![warn(missing_docs)]` is configured for published crates
- broken intra-doc links are treated as errors when feasible (`#![deny(rustdoc::broken_intra_doc_links)]`)
- `[package.metadata.docs.rs]` enables the right features so docs.rs renders the documented API
- private items are documented when they help maintainers, even if the lint does not enforce it

### 6. Examples reflect the public API

Check:

- examples use the recommended public import path (often a prelude)
- examples avoid `unwrap`/`expect` unless the example is about that behavior
- examples avoid hidden lines that mask required setup callers cannot reproduce
- examples cover at least one realistic use, not just a trivial constructor

If doctest *test quality* is the primary concern, defer to `rust-test-quality`. This skill cares whether the example exists, demonstrates the API contract, and uses the right import surface.

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Items missing required sections
- Items with weak descriptions or broken links
- Crate-level or module-level documentation gaps

### Required Fixes
- Sections to add (`# Errors`, `# Panics`, `# Safety`, `# Examples`)
- Intra-doc links to add or repair
- Description rewrites
- Lint or `[package.metadata.docs.rs]` configuration changes

### Optional Improvements
- Examples to strengthen
- Cross-links between related items
