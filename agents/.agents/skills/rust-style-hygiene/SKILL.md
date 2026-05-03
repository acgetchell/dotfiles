---
name: rust-style-hygiene
description: "Enforce idiomatic Rust naming, import usage, and path clarity on changed code. USE FOR: Rust style review, function/method naming critique, import placement and grouping, fully-qualified path simplification, redundant prefix removal (get_, process_, handle_), use-statement organization. DO NOT USE FOR: behavior/correctness review (use rust-test-quality), non-Rust code, generated code, or unchanged files."
---

# rust-style-hygiene

Enforce idiomatic Rust naming, import usage, and path clarity.

## Scope

Focus on:
- newly added or modified Rust code
- function definitions
- import usage and placement

Ignore unrelated, unchanged files.

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

Functions should use **short, unqualified paths**.

Flag:
- fully qualified paths inside functions (e.g., `crate::module::submodule::Type`)
- repeated long paths that reduce readability

Prefer:
- `use` statements + short names
- local clarity over global explicitness

---

### 3. Import Placement

Imports must be placed at the **top of the appropriate module**, not inside functions.

Flag:
- `use` statements inside function bodies
- repeated imports across multiple functions

Exceptions (allowed but should be justified):
- highly localized imports used to avoid namespace pollution
- conditional compilation cases (`cfg`)

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
