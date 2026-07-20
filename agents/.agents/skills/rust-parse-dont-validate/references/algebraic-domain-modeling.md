# Algebraic Domain Modeling

Load this reference when a Rust domain uses modes, booleans, options, strings, parallel fields, or staged states whose combinations are not all valid.

## Choose the Smallest Honest Shape

Prefer:

- an enum for mutually exclusive states
- variant-specific payloads for fields required only in one state
- a tuple struct or newtype for a constrained primitive
- a private struct with a smart constructor for relational field invariants
- a staged builder or proposal type when each step establishes evidence needed by the next

Flag:

- `bool` plus `Option<T>` combinations with impossible states
- enum-like strings or integers in core state
- parallel fields whose valid combinations live only in comments
- repeated branching that rediscovers the same domain category
- accepted/rejected results whose payloads contradict the outcome flag

For example, prefer an enum with `Accepted { ... }`, `Rejected { ... }`, and `NoProposal` variants over an `accepted: bool` accompanied by optional fields whose presence depends on that boolean.

## Preserve Boundary Simplicity

Keep flat raw DTOs when wire compatibility or serialization requires them. Parse them into richer domain enums or newtypes before computation, then convert back only at an output boundary.

Avoid over-modeling:

- do not introduce typestate or deep generics when one enum suffices
- do not wrap a primitive whose invariant is local and cannot escape
- do not make passive reports difficult to inspect
- do not preserve a rich state machine when the operation is genuinely one-step

## Staged Evidence

Use intermediate types such as `Proposal`, `ValidatedConfig`, `PreparedQuery`, or `Transaction` only when they prove a meaningful stage and prevent invalid ordering. Ensure terminal mutation remains explicit and stale intermediates cannot be reused after their owner changes.

Coordinate public chaining ergonomics with `rust-fluent-api-design` and coordinated mutation with `rust-invariant-state-transitions`.
