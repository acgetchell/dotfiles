---
name: rust-api-design
description: "Design, review, and refactor Rust public and cross-crate APIs for cohesive concept ownership, orthogonal capabilities, canonical workflows, minimal surface area, usable downstream contracts, and deliberate compatibility. Use for public modules, types, traits, functions, constructors, adapters, wrappers, aliases, cross-crate boundaries, or repository-wide API architecture; do not use for documentation-only, re-export-only, or implementation-only changes."
---

# Rust API Design

Design Rust APIs as durable caller contracts. Judge the surface from realistic
downstream use, concept ownership, invalid-use prevention, and evolution cost,
not only from the implementation that currently satisfies it.

## Ground Rules

- Read repository guidance and establish the edition, MSRV, supported features,
  downstream consumers, and compatibility promises before judging an API.
- Default to changed public or cross-crate surfaces plus representative callers,
  implementations, tests, and examples. Audit the whole public surface only
  when the user requests a repository-wide or baseline review.
- Preserve compatibility unless the user authorizes a breaking change.
  Distinguish source, behavioral, feature, and ecosystem compatibility.
- Prefer the smallest cohesive surface. Do not add traits, genericity, aliases,
  wrappers, builders, or extension points without a concrete caller benefit.
- Do not mutate Git state unless explicitly requested in the current turn.

This skill owns why a public concept exists, where it belongs, how it composes
with neighboring concepts, which path callers should use, and how the contract
can evolve. Keep documentation completeness under `rust-api-docs`; prelude,
visibility, and re-export mechanics under `rust-prelude-exports`; staged and
fluent workflow ergonomics under `rust-fluent-api-design`; generic constraint
minimality under `rust-trait-bounds`; error taxonomy under
`rust-error-variants`; borrowing and view lifetime under
`rust-borrowed-view-audit`; invalid-state prevention under
`rust-parse-dont-validate`; coordinated mutation under
`rust-invariant-state-transitions`; and semantic test strength under
`rust-test-quality`.

When API analysis exposes one of those concerns, record its caller-visible
consequence and hand off the detailed proof. Do not claim that neighboring
contract is complete from API-design evidence alone.

## Workflow

### 1. Map the public contract

Record the public modules, re-export paths, types, traits, functions, methods,
constructors, associated items, macros, feature-gated surfaces, and external
implementations in scope. Inspect representative downstream call sites,
examples, doctests, integration tests, and dependent crates.

For each material concept, identify:

- its domain responsibility and owning crate or module
- its canonical public path and ordinary caller workflow
- which layer may depend on it
- whether it owns data, borrows a view, adapts another contract, or adds policy
- the compatibility promise and known downstream consumers

Use repository-established public-API snapshots, rustdoc JSON, or
`cargo public-api` when available. Do not install new tooling merely to complete
an ordinary review. Source, Cargo metadata, and compiler behavior remain the
authority.

### 2. Enforce cohesive concept ownership

Check that:

- each public type, trait, and operation has one clear responsibility
- one crate or module owns each domain concept
- lower layers do not depend on downstream domain policy
- adapters live at the integration boundary and add real translation or policy
- wrappers, aliases, and facades do not create competing sources of truth
- implementation types remain private unless callers need their contract
- dependency types are exposed only when that coupling is deliberate

Do not merge concepts merely because their names or fields look similar.
Preserve distinct invariants, units, ownership models, failure contracts, and
semantic roles.

### 3. Keep capability axes orthogonal

Identify independent axes such as ownership, mutation, validation, execution,
backend, dimensionality, policy, and observability. Check whether callers can
compose those axes without an expanding family of parallel types or methods.

Traits should express one coherent capability. Supertraits, associated types,
blanket implementations, sealing, and extension traits should reflect the
actual openness contract rather than convenience for one implementation.
Separate query, mutation, construction, and policy capabilities when their
implementors or callers genuinely vary independently.

### 4. Provide one canonical workflow

Check that ordinary operations have one preferred path and that constructors,
builders, conversion traits, extension methods, free functions, and convenience
wrappers do not compete. Alternate entry points should serve a distinct caller,
compatibility, performance, or integration need and preserve the same contract.

Review adapters and downstream wrappers against their upstream API. Prefer a
direct dependency or deliberate re-export when no semantic translation,
invariant, or policy is added. Prefer an adapter when it isolates a dependency
or translates between genuinely different models.

### 5. Protect evolution paths

Check additions and changes for:

- trait implementation and coherence consequences
- exhaustive enum and struct construction compatibility
- feature-dependent public signatures and accidental API fragmentation
- generic parameter, associated type, and inference stability
- deprecation replacements and workable migration paths
- duplicated concepts that would require synchronized future evolution

Treat a public-API diff as evidence of changed shape, not proof that the new
shape is coherent. Route packaging and semver-policy mechanics to
`rust-cargo-hygiene` and configuration compilation to
`rust-build-portability`.

### 6. Test as a downstream caller

Use the narrowest evidence appropriate to the contract: representative external
consumer builds, public API snapshots or diffs, compile-pass examples, focused
compile-fail cases for rejected misuse, doctests, and affected runtime tests.
Exercise canonical paths rather than importing private modules or relying on
incidental inference.

## Optional Relationship-Graph Assistance

A code or semantic graph may suggest high-centrality abstractions, duplicated
concept clusters, cross-layer edges, or parallel workflows. Treat those results
only as discovery candidates:

- verify visibility, feature gates, re-exports, and exact source declarations
- verify semantic equivalence through callers and contracts, not names or graph
  proximity
- cite the concrete public items and dependency path behind every finding
- keep generated graph artifacts outside the reviewed repository unless the
  user explicitly requests tracked artifacts
- continue with deterministic inspection when the graph tool is absent or fails

The optional tool must not become a prerequisite for this skill or an authority
for publicness, ownership, compatibility, or equivalence.

## Finding Standard

For each finding, show the competing or misplaced public concepts, their current
owners and representative callers, the concrete usability or evolution cost,
and the smallest coherent correction. Classify the disposition as one of:
`keep-distinct`, `consolidate`, `make-private`, `canonicalize`, `re-export`, or
`retain-adapter`. Distinguish confirmed contract defects from design preferences
and avoid aesthetic churn.

## Handoff

Summarize the public surfaces and consumers inspected, concept ownership and
layering decisions, canonical workflows, compatibility constraints, optional
graph assistance used, findings and dispositions, specialist handoffs,
validators and results, remaining migration work, and confirmation that no Git
state mutation occurred when true.
