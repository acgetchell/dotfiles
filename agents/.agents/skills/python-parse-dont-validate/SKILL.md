---
name: python-parse-dont-validate
description: "Design or audit Python domain models and input boundaries using algebraic data types, runtime validation, and preserved static evidence."
---

# Python Parse Don't Validate

Start type-driven design from legal states and operations, then parse weak boundary values into those representations. Combine runtime rejection with static evidence; do not imitate Rust with wrappers that carry no invariant.

## Scope

For design requests, use requirements and representative callers even without code or a diff. For reviews, default to changed code and nearby constructors, parsers, models, and consumers needed to trace evidence. Broaden scope only when requested. Reviews are read-only; preserve compatibility unless breaking changes are authorized.

## Ownership Boundaries

Own invariant-bearing representations, raw-to-trusted conversion, validation errors, and evidence preservation here. Keep public concept ownership and API evolution under `python-api-design`, CLI behavior under `python-cli-review`, mathematical validity under `python-scientific-review`, coordinated mutation and lifecycle under `python-production-review`, test quality under `python-test-quality`, and version/annotation compatibility under `python-build-portability`.

## Workflow

1. Name the invariant, canonical owner, valid cases, forbidden combinations, and whether evidence can expire.
2. Model coexisting facts with products and alternatives with sums carrying case-specific payloads. Keep independent choices independent.
3. Sketch operation inputs and outputs before bodies: require established evidence and return what the next operation needs.
4. Separate raw transport from trusted models; identify runtime predicates the type shape cannot prove.
5. Reject invalid construction before effects, preserve evidence in consumers, and check mutation and restore paths.

For domain modeling or operation design, read the [shared type-driven design guide](../review-graph/references/type-driven-design.md), then [Python modeling rules](references/algebraic-domain-modeling.md).

## Choose Proportionate Representations

Prefer the lightest representation that carries real evidence:

- `TypedDict` or a plain mapping for raw JSON-like transport shapes
- `Enum` or `Literal` for finite choices; unions of variant dataclasses for payload-bearing alternatives
- `NewType` for semantically distinct values where runtime validation is unnecessary or occurs elsewhere
- a frozen slotted dataclass or attrs model with explicit checks for validated compound data
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

Validate required/unknown fields according to policy, dependent values, lengths/dimensions, finite numbers, ranges, categories, paths, and encoding before publishing trusted objects. Annotations, `TypedDict`, `Literal`, and `NewType` do not perform these checks.

## Preserve Static Evidence

Use precise return types and narrow internal APIs, protocols for structural collaborators, and explicit unions for finite alternatives. Check exhaustive consumption with the configured checker and `assert_never` or its supported equivalent; a catch-all is not evidence.

Use `TypeGuard` or `TypeIs` only when a predicate genuinely narrows the value and the evidence is consumed. Prefer `typing.TypeIs` when the repository's declared minimum Python supports it; otherwise follow the project's compatibility policy rather than hard-coding the agent's interpreter version.

Flag casts, ignores, broad mappings, or primitive reconstruction that discard already-proven validation. A type checker passing because data became `Any` is not evidence.

## Keep Trusted Objects Valid

Prefer immutable validated objects; frozen models do not freeze nested collections or aliases. Validate replacements before assignment. Audit direct constructors, defaults, copy/update helpers, deserialization, and bypass APIs. Avoid placeholder invalid defaults, mutable fields checked only in `__post_init__`, mutation-then-validation, and fallible getters over supposedly trusted state.

Bind expiring facts to their owner or recheck at use. Route updates spanning caches, indexes, resources, or objects to `python-production-review`.

## Error Contract

Make rejection informative and consistent with local conventions. Use domain-specific exceptions when callers distinguish categories; use `ValueError` or `TypeError` when simple local callers do not need structured fields.

Include the observed value and expected constraint when safe. Avoid leaking `KeyError`, `AttributeError`, or incidental library exceptions from raw parsing unless documented. Never return `None` for both absence and invalid input when callers need the distinction.

Ensure rejection occurs before partial mutation, file replacement, subprocess publication, or other effects.

## Evidence

Exercise legal cases, materially distinct rejections, numeric boundaries, non-finite values, missing/extra keys, invalid combinations, restore paths, and unchanged state after rejection. Run the configured checker when annotations or models change. Separate runtime rejection from negative typing evidence; passing through `Any` proves neither.

Load `python-test-quality` when test artifacts or evidence design require review; otherwise focused tests remain sufficient.

## Output

For designs, show types, operation signatures, valid/forbidden uses, invariant owners, remaining runtime checks, and migration costs. For reviews, follow the parent contract or report scope and PASS, NEEDS IMPROVEMENT, or FAIL. Order findings by severity: invalid state, admitting boundary, discarded evidence, correction, error contract, and validation. Separate defects from optional redesigns and tested claims from sketches.

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
