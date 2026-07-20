---
name: rust-style-hygiene
description: "Audit Rust code for idiomatic naming, import placement and grouping, path clarity, redundant prefixes, and unnecessary fully qualified paths. Use for focused style and hygiene reviews; route behavior, correctness, documentation, and test-quality concerns to their focused skills."
---

# rust-style-hygiene

Enforce idiomatic Rust naming, import usage, and path clarity.

## Scope

Focus on:
- newly added or modified Rust code
- function definitions
- import usage and placement

Ignore unrelated, unchanged files.

### Scope Modes

Default mode:
- Audit newly added or modified Rust code for naming, imports, and path clarity.
- Ignore unrelated unchanged files.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit naming, import placement, import grouping, redundant prefixes, and path clarity across Rust source, tests, examples, and benches.
- Prioritize findings that affect public API names, repeated import/path friction, generated warnings, or readability in core modules.
- Do not require fixing every historical style issue in one pass; group low-risk cleanup separately.

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
- Concrete, actionable issues with file + function references

### Suggested Fixes
- Specific renames
- Suggested `use` statements
- Suggested path simplifications

### Optional Improvements
- Non-critical cleanup suggestions
