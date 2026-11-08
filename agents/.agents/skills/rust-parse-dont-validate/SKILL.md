---
name: rust-parse-dont-validate
description: "Design or audit Rust domain types and input boundaries using type-driven design and algebraic data types to preserve meaningful invariants."
---

# Rust Parse Don't Validate

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

For direct review invocation, read [references/standalone-workflow.md](references/standalone-workflow.md)
for scope discovery and the complete standalone report.

At design time, start from valid domain states and operations before choosing fields or implementing behavior. Convert raw external representations into types that carry the established invariants inward, so core computation need not repeatedly check raw values.

For a design request, use the supplied requirements and representative callers even when no code or diff exists. For a review, inspect the scoped implementation and distinguish an admitted invalid state from an optional redesign.

## Ground Rules

- Read repository-local conventions for errors, serialization, configuration, public API, and MSRV.
- Name the invariant and its canonical owner before introducing a wrapper.
- Keep passive transport and report shapes simple when core behavior does not trust their fields.
- Do not promise more than a type proves; account for mutation, aliasing, owner-relative facts, lifetimes, deserialization, and unchecked internal paths.
- Keep public concept placement, canonical workflows, and compatibility analysis under `rust-api-design`; own the representation and invariant proof here.
- Keep coordinated multi-field mutation and rollback under `rust-invariant-state-transitions`, error-enum detail under `rust-error-variants`, and lifetime/provenance proof under `rust-borrowed-view-audit`.
- Keep reviews read-only unless fixes are requested. Preserve compatibility unless a breaking change is authorized.

## Conditional References

Load only the detail matching the scoped boundary:

- When designing domain states or signatures, or when fields admit impossible combinations, read the [shared type-driven design guide](../review-graph/references/type-driven-design.md), then [Rust modeling rules](references/algebraic-domain-modeling.md).
- Read [references/nonzero-numeric-refinements.md](references/nonzero-numeric-refinements.md) when positive counts, bounded integers, finite floats, probabilities, tolerances, dimensions, or numeric conversions carry invariants.
- Read [references/serialization-boundaries.md](references/serialization-boundaries.md) when Serde, configuration, wire formats, checkpoints, persistence, or restore paths can bypass constructors.
- Read [references/semgrep-guardrails.md](references/semgrep-guardrails.md) only when the repository already uses Semgrep or similar project rules and the pattern is recurring.

## Workflow

### 1. State the invariant and owner

For each value or related field set, record:

- valid and invalid examples
- lexical, numeric, relational, temporal, contextual, or owner-relative validity
- the type or owner responsible for preserving it
- whether validity can expire after construction
- whether callers need distinct rejection reasons

Do not create a refined type when no meaningful invariant exists or the value is only passive output.

### 2. Design the state space and signatures

Use product types (`struct`/tuples) for facts that coexist and sum types (`enum`) for alternatives with their own required payloads. Enumerate legal cases and representative forbidden combinations before selecting a representation. Keep independent choices independent instead of multiplying variants unnecessarily.

Sketch operation inputs and outputs before bodies: require the evidence an operation needs, and return evidence for the next step. Choose an enum, refined value, or staged type only when it removes a concrete invalid state or operation ordering. State which relationships still require runtime checks; a struct of valid fields does not prove a valid relationship between them.

### 3. Separate raw and domain representations

Keep raw data at boundaries such as CLI arguments, configuration, wire/database formats, C/FFI input, checkpoints, and serialization. Convert it once before core computation.

Prefer:

- a raw DTO for transport
- a fallible parser, `TryFrom`, `FromStr`, smart constructor, or builder `build`
- a domain type with private invariant-bearing state
- infallible observers and computation over the accepted type

Use `From` only for genuinely infallible conversion. Use `Option` for absence, not unexplained rejection. Use a typed `Result` when callers need the reason.

Public fields are appropriate for passive data. They are not a valid domain boundary when arbitrary construction or later assignment can violate behavior-critical relationships.

### 4. Construct valid values only

Audit:

- constructors, factories, parsers, and builders
- `Default`, conversions, struct update, and public fields
- test helpers, literals, crate-private unchecked paths, and migrations
- deserialization and persistence restore

Prefer validation before storage and name raw public construction fallibly (`try_new`, `parse`, `TryFrom`, or `FromStr`). Reserve infallible `new` or `from_*` for already-refined inputs or clearly internal validated paths.

Do not provide a default when no genuine valid default exists. Keep `*_unchecked` narrow, non-public where possible, and documented with the exact precondition.

### 5. Keep accepted values valid

Check that:

- setters and builders validate complete dependent state before commit
- failed updates leave the prior value unchanged
- mutable field, slice, collection, or interior-mutability exposure cannot bypass the owner
- operations are named for valid domain transitions rather than generic mutation when that clarifies the contract
- caches and derived state cannot drift from canonical fields

Use `rust-invariant-state-transitions` when the proof depends on coordinated publication, rollback, operation sequences, or derived state.

### 6. Avoid false or stale proofs

Some facts cannot safely live in a detached wrapper: an index belongs to an owner and generation; a path's existence can change; a handle may belong to one transaction; a borrowed value depends on source lifetime; topology or normalization can be invalidated by mutation.

Bind proof to the owner/generation when practical, keep check and use together when external state can change, or redesign around an owner method. Do not call a wrapper `Valid*` when its property can silently expire.

### 7. Carry evidence inward

After parsing succeeds:

- accept the refined type in internal helpers
- return it from parsers rather than raw data plus a boolean
- keep invariant-backed getters infallible
- avoid converting back to primitives until an actual boundary needs them
- remove duplicated checks only after every construction and mutation path preserves the proof
- handle closed domain variants exhaustively; do not hide an unimplemented case behind a wildcard, fallback, or panic

Keep debug assertions for internal bug detection when useful, but never use panics or assertions as the only rejection mechanism for representable public input.

## Validation

Add focused tests for:

- every meaningful rejection variant and numeric boundary
- default, conversion, parse, deserialize, and round-trip paths that exist
- dependent fields and state-specific payloads
- every legal alternative and operation, plus compiler evidence for forbidden construction or use where practical
- failed mutation preserving the previous value
- raw DTO rejection before core computation
- unchecked internal construction followed by boundary reparsing when such escape hatches deliberately exist
- compile-time visibility or conversion contracts when the repository supports stable compile-fail evidence

Prefer exact error variants and fields over `is_err()`. Use property tests for broad input spaces when they materially improve coverage.

## Design Output

Show the proposed types and operation signatures, representative valid and forbidden uses, the owner and constructor for each invariant, and the runtime checks that remain. Explain any wire/API migration and why a simpler representation is insufficient. Report compiler and runtime evidence separately from an untested design sketch.

## Finding Standard

For each finding, name the invariant, bypass or discarded-proof path, representable invalid state, observable consequence, smallest boundary/type correction, compatibility cost, and regression evidence. Separate confirmed defects from optional modeling improvements.

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
