# Algebraic Domain Modeling in Python

Apply the [shared type-driven design guide](../../review-graph/references/type-driven-design.md)
when designing domain states or signatures, or replacing dependent booleans,
strings, and optional fields. Static restrictions and runtime guarantees are
different claims in Python.

## Map the Model to Python

Use dataclasses or tuples for products and explicit unions of distinct variants
for payload-bearing alternatives. Map the shared delivery example to a `Ship`
dataclass requiring `address: Address`, a `Pickup` dataclass requiring
`point: PickupPointId`, and a `Delivery = Ship | Pickup` alias. Use the project's
Python-compatible union/alias syntax.

That shape rules out missing payloads for checked callers, not invalid address
contents or an unsupported item/destination pairing. Validate those predicates
at their canonical construction or operation boundary. An annotation alone
cannot prove them.

Keep `Enum` or `Literal` for alternatives without different payloads, and
`T | None` for genuine optional presence. A tagged `TypedDict` union with
`Literal` discriminants can describe wire data, but does not validate JSON.
Prefer a finite union over a broad base class when the domain is closed. An
open hierarchy or protocol describes collaborators without enumerating states.

## Carry Evidence Without Promising Linear Ownership

A parser returning `Delivery` after runtime checks carries more evidence than
raw fields plus `is_valid: bool`. If only a `PreparedOrder` can be submitted,
accept that type instead of a generic order with an unchecked status string.
Return the supported next state or follow the project's informative
exception/result convention.

Python has no affine ownership: a transition annotation does not consume old
aliases or prevent repeated submission. Enforce single-use behavior at the
owning resource when required. Bind intermediate evidence to owner/generation
when it can become stale. Route cross-object commit, cleanup, and rollback to
`python-production-review`; a stage type alone cannot prove them.

## Make Runtime Guarantees Honest

- Annotations, aliases, `NewType`, `Literal`, and `TypedDict` do not reject
  runtime input. `NewType` distinguishes static meanings; it does not establish
  a predicate. `cast` changes the checker's view, not the value.
- Dataclass-generated constructors do not enforce annotated field types.
  Decide whether supported direct construction performs runtime checks or is
  internal behind a parser; do not advertise an underscore as access control.
  Audit every supported construction, deserialize, and update path.
- `frozen=True` and slots are not deep immutability or a security boundary.
  Copy mutable input into immutable owned data when required; consider nested
  mutation and aliases even if the outer object cannot be assigned to.
- Existing attrs/Pydantic models may provide checks, but inspect coercion,
  strictness, defaults, assignment, and reconstruction behavior. Pydantic
  `model_construct` and unvalidated copy/update paths can bypass a parser's
  promises. Keep dependency/version-specific behavior explicit.
- A narrowing predicate must prove exactly what it claims. `TypeGuard` or
  `TypeIs` alone does not validate, freeze aliases, or preserve a fact after
  mutation. Keep check and use together when evidence can be invalidated.

Enforce the supported boundary contract rather than trying to defeat deliberate
reflection or monkeypatching everywhere. State which callers are assumed to be
type-checked and which boundary checks protect untyped callers.

## Exhaustiveness Is Checked, Not Assumed

For a closed union, narrow with `isinstance`, a supported discriminant, or class
patterns. Finish an otherwise-unhandled path with `assert_never(value)` and run
the configured checker, or use its established exhaustive-match diagnostics.
Use `typing.assert_never` only when the supported Python floor permits it;
otherwise follow the project's existing compatibility approach.

A plain `match`, final `else`, wildcard, or runtime exception does not by itself
prove static exhaustiveness. Do not cast to `Never`, suppress diagnostics, or
widen to `Any` to make the proof pass. Guards can leave valid values unmatched.
An open protocol may need an unknown case; reject or preserve it deliberately
rather than treating it as a known successful state.

## Python Evidence

Use durable negative typing tests when the repository supports them; otherwise
report the limited checker experiment honestly. Separately exercise runtime
malformed input, relational predicates, supported direct construction, nested
mutation/aliasing, copy/restore paths, and failed updates. Type-checking success
does not prove runtime rejection, and runtime tests do not establish static
exhaustiveness.

Keep flat DTOs when wire compatibility requires them. Avoid new dependencies,
typestate hierarchies, or per-field wrappers when a union, existing validated
model, or local check suffices.
