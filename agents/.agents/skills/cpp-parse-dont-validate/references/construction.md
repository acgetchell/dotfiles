# C++ Domain Construction

## Choose the smallest proof-bearing representation

Use ordinary C++ facilities before inventing a framework:

- `enum class` instead of string or integer modes in core logic
- a small value class with private state for a constrained primitive
- `std::optional<T>` for genuine absence
- `std::variant<...>` for mutually exclusive states with variant-specific data
- separate named ID or unit types when accidental interchange is a real risk
- a validated aggregate when several fields establish one relational invariant

Do not mistake an unsigned integer for proof of positivity or safe conversion.
Check negative inputs before conversion, perform narrowing deliberately, and
handle limits without overflow. For floating-point constraints, state the
policy for NaN, infinities, signed zero, endpoints, and normalization tolerance.

Avoid a class per primitive when the invariant is local, cannot escape, and is
already enforced by one clear boundary.

## Construct valid objects only

Audit every creation path:

- constructors and static factories
- default, copy, and move operations
- builders and fluent APIs
- deserialization and persistence restore
- test helpers, literals, and internal unchecked functions
- conversion from foreign or C-compatible structs

Prefer a private or otherwise restricted representation plus one deliberate
raw-to-domain path. Select its failure shape from the local contract:

- `std::expected<T, E>` when C++23 and the supported libraries provide it
- the repository's existing result/status type when established
- a typed exception for constructor-style APIs in an exception-based codebase
- `std::optional<T>` only when absence is the complete and useful explanation

Make raw-value converting constructors `explicit`. When failure must be returned
as a value, use a named static factory or free parser because a constructor cannot
return an error result. Do not let an implicit conversion hide validation,
allocation, or failure behavior at a call site.

Reserve infallible construction for inputs whose types already carry the needed
proof. Name unchecked paths explicitly, keep them narrow, and document the
precondition; do not let tests or deserializers make them the ordinary route.

Do not provide a default constructor unless a genuine valid default state
exists. If a moved-from object remains observable, ensure its operations honor
the type's documented valid-but-unspecified or restricted post-move contract.
