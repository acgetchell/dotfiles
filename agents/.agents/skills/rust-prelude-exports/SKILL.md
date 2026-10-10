---
name: rust-prelude-exports
description: "Review Rust preludes, visibility, and re-exports when downstream import paths or public surface boundaries change."
---

# rust-prelude-exports

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

Audit Rust prelude modules and public re-export surfaces for minimality, orthogonality, and usability.

A good prelude makes examples and downstream code pleasant without turning into a dumping ground. It should expose the concepts users need to compose the crate's public API, while keeping specialized domains separate enough that imports remain obvious.

This skill owns the intentional export and import surface. Route feature/target combinations that fail to compile or expose inconsistent cfg-selected APIs to `rust-build-portability`.

## Scope

Focus on newly added or modified Rust public APIs that affect:

- `pub mod prelude`
- scoped preludes such as `prelude::geometry`, `prelude::simulation`, `prelude::testing`, or feature-specific preludes
- `pub use` exports from `lib.rs` or module roots
- doctest imports
- integration test imports
- example and benchmark imports
- new types/functions/traits that users need to access from outside the crate

Ignore private implementation imports unless they reveal a missing or confused public export.

For direct invocation, read [the standalone workflow](references/standalone-workflow.md).

## Review goals

### 1. Minimal exports

The prelude should include what users routinely need to write clear downstream code.

Flag:

- exporting every type from a module without a usage reason
- re-exporting implementation details, backend internals, or unstable helpers
- adding niche test-only or benchmark-only utilities to the main prelude
- exporting both a type and multiple redundant aliases unless each has a clear role

Prefer:

- public domain types, traits, constructors, and errors needed by normal usage
- narrow scoped preludes for specialized workflows
- explicit imports for rare or expert-only APIs

### 2. Orthogonal preludes

Different preludes should have clear boundaries and should not compete with each other.

Check:

- each scoped prelude has a coherent audience or workflow
- overlap between preludes is intentional and small
- names do not collide or create ambiguous imports
- generic `prelude::*` does not make scoped preludes unnecessary or confusing

Flag:

- the same large set of exports copied into multiple scoped preludes
- prelude names that imply one domain but export unrelated items
- broad preludes that pull in both construction, simulation, testing, and backend internals

### 3. Downstream usage

Use doctests, integration tests, examples, or benchmarks that exercise the changed
public import path. Common workflows may use a main or scoped prelude; specialist
APIs can use direct public module imports. Repeated awkward imports can indicate
a missing scoped prelude, but do not justify exporting internals automatically.

Check that examples compile without private modules, hidden in-crate context,
or `super::*` imports unavailable to downstream users. Choose the smallest
consumer example that demonstrates the actual export contract.

### 4. Module organization and visibility

The public re-export surface is only useful if the underlying modules expose the right items at the right scope. Review module organization and visibility together with the prelude.

Check:

- public modules contain items that meaningfully belong together for downstream users
- internal helpers use `pub(crate)` or `pub(super)` instead of bare `pub` when they should not appear in the public API
- `pub use` re-exports do not accidentally widen visibility from `pub(crate)` to `pub`
- `#[cfg(...)]` and feature gates are applied consistently to a module and its re-exports
- doc-only items (e.g., examples, README-style modules) are not exported into the public surface

Flag:

- `pub fn`/`pub struct` on items that only the crate uses
- a tightly-scoped module gating items with `pub(crate)` while a sibling re-exports them as `pub`
- feature-gated items whose re-export is not feature-gated, leaving broken links when the feature is off
- private modules (`mod foo;`) referenced from doctests or examples that downstream users cannot reach

### 5. Public API stability and feature boundaries

Preludes are part of the crate's user-facing surface.

Check:

- exports are gated consistently with feature flags
- docs mention which prelude to use for common workflows
- adding an export does not accidentally stabilize an internal type
- removing or moving an export is treated as a breaking change when appropriate

### 6. Validation

When exports change, validate the intended public import paths and relevant
feature boundaries with downstream-style evidence. Reuse an existing doctest or
consumer check when it proves that contract. Document each scoped prelude's
purpose; do not duplicate equivalent examples just to satisfy a report format.
