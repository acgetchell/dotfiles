---
name: rust-prelude-exports
description: "Audit Rust prelude modules and public re-export surfaces for minimality, orthogonality, and usability in doctests, integration tests, examples, and benchmarks on changed APIs or whole-repo baseline audits when explicitly requested. USE FOR: Rust review comments asking whether new functionality has appropriate prelude exports, designing crate::prelude modules, scoped preludes (geometry/simulation/testing), public use/re-export decisions, doctest import ergonomics, integration test/example/benchmark import surfaces, avoiding bloated or overlapping preludes. DO NOT USE FOR: Rust naming/import style inside implementation code (use rust-style-hygiene), test quality itself (use rust-test-quality), error design (use rust-error-variants), non-Rust code, or unrelated unchanged APIs unless a baseline audit is requested."
---

# rust-prelude-exports

Audit Rust prelude modules and public re-export surfaces for minimality, orthogonality, and usability.

A good prelude makes examples and downstream code pleasant without turning into a dumping ground. It should expose the concepts users need to compose the crate's public API, while keeping specialized domains separate enough that imports remain obvious.

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

### Scope Modes

Default mode:
- Audit newly added or modified public APIs, preludes, `pub use` exports, and downstream-style imports.
- Ignore unrelated unchanged exports unless they define the boundary the changed API should follow.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit the complete public export surface, all prelude modules, doctest imports, integration tests, examples, and benchmark imports.
- Prioritize findings by accidental API stabilization, bloated or overlapping preludes, missing ergonomic exports for common workflows, and examples that require internal paths.
- Do not require fixing every historical export nit in one pass; separate breaking cleanup from additive ergonomic fixes.

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

### 3. Doctest ergonomics

Doctests should demonstrate the intended public import path.

Check that new public APIs can be used in doctests with concise imports, for example:

- `use crate_name::prelude::*;` for common workflows
- `use crate_name::prelude::geometry::*;` for backend/geometry-specific examples
- direct module imports when the API is intentionally not prelude-worthy

Flag:

- doctests requiring long chains of internal module paths for ordinary usage
- doctests importing private or unstable modules
- examples using `super::*` patterns that downstream users cannot copy
- doctests that only compile because of hidden in-crate context

### 4. Integration tests, examples, and benchmarks

Integration tests, examples, and benchmarks act like downstream users. Their imports should validate the public surface.

Check:

- integration tests use public crate paths rather than internal-only modules
- examples show the recommended import style
- benchmarks import exactly the APIs needed to construct realistic workloads
- repeated awkward import bundles point to a missing scoped prelude

Flag:

- many files repeating the same long list of imports
- examples importing from deep internal modules for core use cases
- benchmarks relying on non-public helpers that downstream users cannot access

### 5. Module organization and visibility

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

### 6. Public API stability and feature boundaries

Preludes are part of the crate's user-facing surface.

Check:

- exports are gated consistently with feature flags
- docs mention which prelude to use for common workflows
- adding an export does not accidentally stabilize an internal type
- removing or moving an export is treated as a breaking change when appropriate

### 7. Tests and documentation

When prelude/export behavior changes, add tests or docs that lock in the intended surface.

Prefer:

- doctests that compile using the new prelude path
- integration tests that import from the public prelude
- examples updated to use the recommended scoped prelude
- documentation comments explaining what each scoped prelude is for

Avoid tests that only compile because they live inside the same module as the implementation.

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Concrete issues with file/module references
- For each issue, state whether the problem is missing export, excessive export, overlap, unclear scope, or downstream usability

### Required Fixes
- Exports to add
- Exports to remove or move to a scoped prelude
- Visibility tightenings (`pub` → `pub(crate)` or `pub(super)`) for items that should not be public
- Scoped preludes to create or rename
- Doctests, integration tests, examples, or benchmarks to update
- Documentation to add for prelude usage

### Optional Improvements
- Non-blocking organization, naming, or docs refinements
