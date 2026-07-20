---
name: rust-parse-dont-validate
description: "Audit Rust boundary parsing and invalid-state prevention with proof-bearing domain types. Use for smart constructors, private invariant-bearing fields, fallible setters and builders, raw DTO conversion, deserialization, refined numeric or enum types, validation evidence, infallible getters, and APIs where invalid values remain representable or validation is repeated after acceptance."
---

# Rust Parse Don't Validate

Convert raw external representations into domain types that can represent only supported states. Let core computation accept those types and rely on their invariants instead of repeatedly checking raw values.

## Ground Rules

- Read repository-local conventions for errors, serialization, configuration, public API, and MSRV.
- Name the invariant and its canonical owner before introducing a wrapper.
- Keep passive transport and report shapes simple when core behavior does not trust their fields.
- Do not promise more than a type proves; account for mutation, aliasing, owner-relative facts, lifetimes, deserialization, and unchecked internal paths.
- Keep coordinated multi-field mutation and rollback under `rust-invariant-state-transitions`, error-enum detail under `rust-error-variants`, and lifetime/provenance proof under `rust-borrowed-view-audit`.
- Keep reviews read-only unless fixes are requested. Preserve compatibility unless a breaking change is authorized.

## Conditional References

Load only the detail matching the scoped boundary:

- Read [references/algebraic-domain-modeling.md](references/algebraic-domain-modeling.md) when booleans, options, strings, parallel fields, modes, or staged states admit impossible combinations.
- Read [references/nonzero-numeric-refinements.md](references/nonzero-numeric-refinements.md) when positive counts, bounded integers, finite floats, probabilities, tolerances, dimensions, or numeric conversions carry invariants.
- Read [references/serialization-boundaries.md](references/serialization-boundaries.md) when Serde, configuration, wire formats, checkpoints, persistence, or restore paths can bypass constructors.
- Read [references/semgrep-guardrails.md](references/semgrep-guardrails.md) only when the repository already uses Semgrep or similar project rules and the pattern is recurring.

## Scope Modes

Use changed-code mode by default. Inspect changed invariant-bearing types and nearby constructors, parsers, mutators, and consumers.

Use pull-request mode for a named PR, branch, or diff base. Prioritize new public boundaries, invalid stored states, discarded validation evidence, and missing rejection tests.

Use whole-repository baseline mode only when explicitly requested. Start with public construction, configuration, deserialization, setters, and repeated validation helpers; group findings by owning type.

## Workflow

### 1. State the invariant and owner

For each value or related field set, record:

- valid and invalid examples
- lexical, numeric, relational, temporal, contextual, or owner-relative validity
- the type or owner responsible for preserving it
- whether validity can expire after construction
- whether callers need distinct rejection reasons

Do not create a refined type when no meaningful invariant exists or the value is only passive output.

### 2. Separate raw and domain representations

Keep raw data at boundaries such as CLI arguments, configuration, wire/database formats, C/FFI input, checkpoints, and serialization. Convert it once before core computation.

Prefer:

- a raw DTO for transport
- a fallible parser, `TryFrom`, `FromStr`, smart constructor, or builder `build`
- a domain type with private invariant-bearing state
- infallible observers and computation over the accepted type

Use `From` only for genuinely infallible conversion. Use `Option` for absence, not unexplained rejection. Use a typed `Result` when callers need the reason.

Public fields are appropriate for passive data. They are not a valid domain boundary when arbitrary construction or later assignment can violate behavior-critical relationships.

### 3. Construct valid values only

Audit:

- constructors, factories, parsers, and builders
- `Default`, conversions, struct update, and public fields
- test helpers, literals, crate-private unchecked paths, and migrations
- deserialization and persistence restore

Prefer validation before storage and name raw public construction fallibly (`try_new`, `parse`, `TryFrom`, or `FromStr`). Reserve infallible `new` or `from_*` for already-refined inputs or clearly internal validated paths.

Do not provide a default when no genuine valid default exists. Keep `*_unchecked` narrow, non-public where possible, and documented with the exact precondition.

### 4. Keep accepted values valid

Check that:

- setters and builders validate complete dependent state before commit
- failed updates leave the prior value unchanged
- mutable field, slice, collection, or interior-mutability exposure cannot bypass the owner
- operations are named for valid domain transitions rather than generic mutation when that clarifies the contract
- caches and derived state cannot drift from canonical fields

Use `rust-invariant-state-transitions` when the proof depends on coordinated publication, rollback, operation sequences, or derived state.

### 5. Avoid false or stale proofs

Some facts cannot safely live in a detached wrapper: an index belongs to an owner and generation; a path's existence can change; a handle may belong to one transaction; a borrowed value depends on source lifetime; topology or normalization can be invalidated by mutation.

Bind proof to the owner/generation when practical, keep check and use together when external state can change, or redesign around an owner method. Do not call a wrapper `Valid*` when its property can silently expire.

### 6. Carry evidence inward

After parsing succeeds:

- accept the refined type in internal helpers
- return it from parsers rather than raw data plus a boolean
- keep invariant-backed getters infallible
- avoid converting back to primitives until an actual boundary needs them
- remove duplicated checks only after every construction and mutation path preserves the proof

Keep debug assertions for internal bug detection when useful, but never use panics or assertions as the only rejection mechanism for representable public input.

## Validation

Add focused tests for:

- every meaningful rejection variant and numeric boundary
- default, conversion, parse, deserialize, and round-trip paths that exist
- dependent fields and state-specific payloads
- failed mutation preserving the previous value
- raw DTO rejection before core computation
- unchecked internal construction followed by boundary reparsing when such escape hatches deliberately exist
- compile-time visibility or conversion contracts when the repository supports stable compile-fail evidence

Prefer exact error variants and fields over `is_err()`. Use property tests for broad input spaces when they materially improve coverage.

## Finding Standard

For each finding, name the invariant, bypass or discarded-proof path, representable invalid state, observable consequence, smallest boundary/type correction, compatibility cost, and regression evidence. Separate confirmed defects from optional modeling improvements.

## Handoff

Summarize boundaries and invariant owners reviewed, proof-bearing types, bypass paths closed, routed state/error/lifetime work, tests and validators, files changed, and confirmation that no git state mutation occurred when true.
