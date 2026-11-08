# Algebraic Domain Modeling in Rust

Apply the [shared type-driven design guide](../../review-graph/references/type-driven-design.md)
when designing domain states or signatures, or when modes, booleans, options,
strings, parallel fields, or staged states admit invalid combinations.

## Map the Model to Rust

Prefer:

- a struct or tuple for coexisting facts
- an enum for alternatives with variant-specific required payloads
- a tuple struct or newtype for a constrained primitive
- a private struct with a smart constructor for relational field invariants
- a staged builder or proposal type when each step establishes evidence needed
  by the next

Map the shared delivery example to `Delivery::Ship { address: Address }` and
`Delivery::Pickup { point: PickupPointId }`. `Option<T>` and `Result<T, E>`
already model absence and success/failure; use domain enums for different
meanings. For example, prefer `Accepted { ... }`, `Rejected { ... }`, and
`NoProposal` over an acceptance flag plus optional outcome fields.

Flag enum-like strings/integers in core state, parallel fields whose valid
combinations live only in comments, and repeated branching that rediscovers
the same domain category. Use standard refinements such as `NonZeroUsize`
before inventing equivalents. Keep relational fields private and validate them
together; an enum does not repair publicly constructible invalid payloads.

## Encode Meaningful Stages

An operation needing `PreparedOrder` should accept that type rather than an
arbitrary order and recheck its stage. Return a supported next state or a typed
failure instead of mutating a status flag while leaving old payloads accessible.

Choose an ordinary enum when the stage is selected at runtime or heterogeneous
values must be stored together. Choose separate stage types or typestate when
callers materially benefit from rejecting unavailable operations at compile
time. Consuming a non-`Copy` value can enforce a local transition, but `Clone`,
aliases, or duplicated external handles can defeat an intended one-use promise.
Do not confuse move semantics with transactional or global uniqueness proofs.

For transition failure, specify whether the caller retains the old state, gets
it back with the error, or deliberately loses it. Ensure terminal mutation is
explicit and stale intermediates cannot be reused after their owner changes.
Coordinate public chaining ergonomics with `rust-fluent-api-design`, coordinated
publication/rollback with `rust-invariant-state-transitions`, and lifetime or
provenance evidence with `rust-borrowed-view-audit`.

## Handle Cases Exhaustively

Match closed domain enums exhaustively so adding a case reveals affected
consumers. Avoid `_`, `unreachable!()`, or default behavior that conceals a
missing legal case. Guards may leave cases uncovered; check the actual match.

An external `#[non_exhaustive]` enum requires a fallback. Open wire protocols
may also need an explicit unknown case. Give that path deliberate rejection or
supported behavior; do not silently turn unknown input into a successful known
state. Coordinate public enum evolution with `rust-api-design` rather than
breaking downstream matches just to close the internal model.

## Preserve Boundary Simplicity

Keep flat raw DTOs when wire compatibility or serialization requires them.
Convert to domain enums or newtypes before computation and back at the output
boundary. Apply [serialization boundaries](serialization-boundaries.md) when
Serde or restore paths could bypass construction; private fields alone do not
prevent derived deserialization from accepting invalid relationships.

Do not introduce deep generics or typestate when one enum suffices, wrap a
primitive whose invariant is local and cannot escape, make passive reports
hard to inspect, or retain a rich state machine for a genuinely one-step
operation.

## Rust Evidence

Compile ordinary callers for each legal case. Use existing compile-fail
facilities where practical to exercise private construction, wrong-state
operations, and conversion restrictions. Confirm diagnostics reject the
intended misuse, not missing imports or unrelated errors.

Test remaining predicates, parse/deserialize/restore paths, and failure that
preserves the previous value separately. Exhaustiveness does not establish
predicate correctness, persistence compatibility, or freshness of
owner-relative evidence.
