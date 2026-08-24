---
name: rust-api-docs
description: "Audit Rust API documentation for completeness, required Errors, Panics, Safety, and Examples sections, intra-doc links, crate and module docs, docs.rs visibility, and non-trivial private helper intent behind public behavior. Use for public documentation coverage and semver-relevant doc changes; route executable doctest evidence to rust-test-quality."
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
- rely on changed private helpers whose intent is necessary to understand or
  safely maintain the public contract

Ignore unrelated private items. Review changed private helpers when they support,
constrain, or explain public API behavior, especially when they encode error
classification, panic/rollback invariants, proposal semantics, serialization
compatibility, or other behavior callers observe indirectly.

When invoked directly without an exact parent scope and result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md).
Graph and Rust-orchestrator dispatches use their supplied scope and compact
result contract without loading that reference.

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

### 5. API-supporting private helper docs

This skill is primarily about public rendered documentation, but changed private
helpers can be part of API documentation quality when they carry the logic behind
public contracts. Do not defer these automatically.

For changed private functions, methods, and helper types that support public API
behavior, check for `///` comments explaining:

- why the helper exists (intent)
- what it does (behavior)
- which public contract, invariant, or observable behavior it protects when that
  is non-obvious

Flag:

- missing docs on non-trivial changed helpers behind public APIs
- comments that only restate the helper name
- helper docs that explain implementation mechanics but omit the public contract
  or invariant they protect
- changed private helpers that should be covered by
  `RUSTDOCFLAGS='-D warnings -D missing-docs' cargo doc --workspace --no-deps --document-private-items`

For broad private-helper coverage, test assertion quality, doctest realism, or
panic-path testing, coordinate with `rust-test-quality`.

### 6. Lints and configuration

Check:

- `#![deny(missing_docs)]` or `#![warn(missing_docs)]` is configured for published crates
- broken intra-doc links are treated as errors when feasible (`#![deny(rustdoc::broken_intra_doc_links)]`)
- `[package.metadata.docs.rs]` enables the right features so docs.rs renders the documented API
- private items are documented when they help maintainers or protect public API
  contracts, even if the lint does not enforce it

### 7. Examples reflect the public API

Check:

- examples use the recommended public import path (often a prelude)
- examples avoid `unwrap`/`expect` unless the example is about that behavior
- examples avoid hidden lines that mask required setup callers cannot reproduce
- examples cover at least one realistic use, not just a trivial constructor

If doctest *test quality* is the primary concern, defer to `rust-test-quality`. This skill cares whether the example exists, demonstrates the API contract, and uses the right import surface.
