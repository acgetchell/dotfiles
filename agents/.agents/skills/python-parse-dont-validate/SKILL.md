---
name: python-parse-dont-validate
description: "Audit Python boundary parsing and invalid-state prevention. Use for raw dictionaries, strings, counts, paths, optionals, CLI or environment values, subprocess output, JSON, CSV, TOML, YAML, dataclasses, attrs, Pydantic, Enum, Literal, NewType, TypedDict, and type-checkable domain invariants. Route general application behavior, scientific validity, packaging, and test design to focused skills."
---

# Python Parse Don't Validate

Parse untrusted or weakly typed boundary values into representations trusted by core code. Combine runtime rejection at the boundary with useful static evidence; do not imitate Rust with wrappers that add ceremony but carry no invariant.

## Scope

Use changed-code mode by default. Inspect nearby constructors, parsers, models, and consumers only far enough to determine where validation evidence is created or lost. Use branch or whole-repository scope only when requested.

## Ownership Boundaries

- Own raw-to-trusted conversion, invariant-bearing models, finite categories, optional-state modeling, validation errors, and preservation of validation evidence here.
- Let `python-cli-review` own user-visible argument and output behavior.
- Let `python-scientific-review` own whether a mathematical invariant is correct; retain boundary enforcement here.
- Let `python-production-review` own coordinated multi-component mutation, lifecycle, and residual state transitions beyond a single validated object.
- Let `python-test-quality` own test structure and evidence quality.

## Workflow

1. Name the invariant and the boundary where weak values enter.
2. Identify the raw transport shape and the trusted internal representation.
3. Verify conversion rejects every materially distinct invalid state before effects or computation.
4. Trace whether callers preserve the resulting type evidence or widen it back to primitives and `Any`.
5. Check that mutation cannot invalidate a previously trusted object.

## Choose Proportionate Representations

Prefer the lightest representation that carries real evidence:

- `TypedDict` or a plain mapping for raw JSON-like transport shapes
- `Enum` or `Literal` for finite choices
- `NewType` for semantically distinct values where runtime validation is unnecessary or occurs elsewhere
- a frozen slotted dataclass or attrs model for validated compound data
- Pydantic only when the project already depends on it or its boundary features materially help
- `Path` plus explicit checks for path constraints
- a named parser such as `parse_*`, `from_raw`, `load_*`, or local convention

Do not create domain wrappers for passive report records, one-use values with no semantic constraint, or shapes callers only display.

## Parse At Boundaries

Flag raw values passed deep into trusted computation:

- `dict[str, Any]` or untyped API data
- environment and configuration strings
- CSV/JSON/TOML/YAML records
- subprocess stdout
- filesystem paths with containment, existence, or kind requirements
- raw modes, IDs, units, counts, probabilities, or optional combinations

Validate required fields, unknown fields according to policy, mutually dependent values, length/dimension agreement, finite numbers, ranges, categories, path constraints, and encoding before publishing the trusted object.

## Preserve Static Evidence

Prefer precise return types and narrow internal APIs. Use protocols for structural collaborators, enums/literals for finite branches, and separate variant dataclasses when combinations of optionals encode distinct states.

Use `TypeGuard` or `TypeIs` only when a predicate genuinely narrows the value and the evidence is consumed. Prefer `typing.TypeIs` when the repository's declared minimum Python supports it; otherwise follow the project's compatibility policy rather than hard-coding the agent's interpreter version.

Flag casts, ignores, broad mappings, or primitive reconstruction that discard already-proven validation. A type checker passing because data became `Any` is not evidence.

## Keep Trusted Objects Valid

Prefer immutable validated objects. When mutation is necessary, validate the replacement before assignment. Avoid mutable public fields whose invariants exist only in `__post_init__`, placeholder invalid defaults, setters that mutate then validate, and getters that may fail because stored state is not trustworthy.

For updates spanning caches, indexes, external resources, or several objects, hand coordinated commit and rollback analysis to `python-production-review` after establishing the per-object invariant here.

## Error Contract

Make rejection informative and consistent with local conventions. Use domain-specific exceptions when callers distinguish categories; use `ValueError` or `TypeError` when simple local callers do not need structured fields.

Include the observed value and expected constraint when safe. Avoid leaking `KeyError`, `AttributeError`, or incidental library exceptions from raw parsing unless documented. Never return `None` for both absence and invalid input when callers need the distinction.

Ensure rejection occurs before partial mutation, file replacement, subprocess publication, or other effects.

## Evidence

Exercise acceptance and each materially distinct rejection reason, boundary values, non-finite numbers, missing or extra keys, invalid combinations, and unchanged state after rejected updates when relevant. Run the configured type checker when annotations or invariant-carrying models change.

Load `python-test-quality` when test artifacts or evidence design require review; otherwise focused tests remain sufficient.

## Output

State the scope and PASS, NEEDS IMPROVEMENT, or FAIL. Order findings by severity and identify the invalid state, boundary that admits it, evidence discarded, proposed trusted representation, error contract, and focused validation needed.
