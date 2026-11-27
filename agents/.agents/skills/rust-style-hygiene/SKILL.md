---
name: rust-style-hygiene
description: "Review Rust naming and imports as a standard Rust review pass or for focused style and readability work."
---

# rust-style-hygiene

Enforce idiomatic Rust naming, import usage, and path clarity.

Use this lens in every orchestrated Rust review that contains Rust code or
examples, as well as for focused style/readability work. Apply repository import
and naming conventions to private implementation changes too. Keep optional
preferences distinct from correctness or production-readiness blockers.

## Scope

Focus on:

- newly added or modified Rust code
- function definitions
- import usage and placement

Ignore unrelated, unchanged files.

### Scope Modes

Default mode:

- Audit naming, imports, and path clarity in newly added or modified Rust code,
  including private implementation changes and code examples.
- Ignore unrelated unchanged files.

Whole-repo baseline mode:

- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit naming, import placement, import grouping, redundant prefixes, and path clarity across every captured `.rs` file,
  including nested workspace members, build scripts, and fixtures.
- Check [repository file conventions](#repository-file-conventions) against that same inventory.
- Prioritize findings that affect public API names, repeated import/path friction, generated warnings, or readability in core modules.
- Do not require fixing every historical style issue in one pass; group low-risk cleanup separately.

### Repository File Conventions

Identify required file conventions from applicable repository guidance or a
maintained checker. Use the Rust inventory already captured for the review,
including selected fixtures and other files outside Cargo targets where the
rule applies. Prefer the repository's own checker. Reuse results that already
cover the applicable paths under the same rule and source state. Inspect paths
that lack matching checker evidence. Cite the repository rule and each affected
path.

Cargo and crate-root lints establish effective compiler policy. Require a
per-file declaration such as `#![forbid(unsafe_code)]` only where the repository
specifies it. Repeated headers in nearby files can guide discovery of a local
rule. Use [the file-conventions fixture](scripts/file-conventions-fixture.sh)
when validating this skill's behavior.

---

## Requirements

### 1. Function Naming (Concise and Idiomatic)

Function names must be:

- concise
- descriptive
- idiomatic (snake_case)

Flag:

- overly long names (e.g., `compute_the_total_sum_of_all_elements`)
- redundant prefixes (e.g., `get_`, `process_`, `handle_` unless meaningful)
- names that repeat module context unnecessarily

Prefer:

- `sum` over `compute_sum`
- `normalize` over `normalize_data_values`
- `insert` over `insert_item_into_collection`

---

### 2. Path Usage (Short and Readable)

Prefer short imported paths when repetition harms readability, while preserving qualification when it disambiguates names, documents an uncommon origin, or keeps a one-off use clearer.

Flag repeated fully qualified paths inside functions when they obscure the operation or duplicate the same importable prefix.

Prefer:

- `use` statements + short names
- local clarity over global explicitness

---

### 3. Import Placement

Prefer imports at the narrowest module scope that remains clear and avoids repetition.

Flag repeated function-local imports, production-scope test imports, or broad module imports that create ambiguity or unused names.

Accept localized imports when they avoid namespace pollution, clarify trait-method activation, or isolate conditional compilation.

---

### 4. Import Organization

Imports should be:

- grouped logically (std, external crates, local modules)
- deduplicated
- minimal (no unused imports)

---

### 5. Performance-Sensitive Code (if applicable)

Avoid unnecessary imports or abstractions that obscure:

- hot paths
- tight loops
- numeric kernels

Clarity must not degrade performance reasoning.

---

## Output Format

### Summary

- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings

- Concrete, actionable issues with file and line or symbol references

### Suggested Fixes

- Specific renames
- Suggested `use` statements
- Suggested path simplifications

### Optional Improvements

- Non-critical cleanup suggestions

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
