# Callable and Failure Composition

## Compose callables deliberately

Prefer named functions for reusable domain operations and small lambdas for
local glue. For every callable:

- capture only what it needs, by reference or value according to lifetime
- use `mutable` only when stateful callable behavior is part of the contract
- constrain only the call form and argument/return requirements the API needs,
  using `std::invocable`, `std::predicate`, `std::regular_invocable`, or a small
  project concept when a public generic API benefits from it
- use templates or `auto` parameters for static composition; use
  `std::function` only when runtime type erasure, storage, or ABI shape warrants
  its allocation and indirection costs
- avoid returning lambdas that capture local references

Do not build a generic combinator framework when two named functions express
the domain more directly.

## Keep failure in the data flow

Follow the repository's established error model. Keep expected rejection,
absence, exceptions, and invariant violations distinct.

- compose fallible stages without discarding structured errors
- avoid converting failure to `bool` or `std::optional` when callers need the
  reason
- avoid throwing inside algorithm predicates or transformations unless the
  surrounding exception contract and partial-work behavior are deliberate
- validate raw inputs before starting a transformation that publishes output
- keep accessors and later transformations infallible once a validated type
  carries the required invariant

Use `cpp-parse-dont-validate` when the pipeline repeatedly checks raw input or
should begin from a proof-bearing domain type. Use
`cpp-exception-safety-error-contracts` when exceptions, `noexcept`, rollback, or
partial output require a dedicated audit.
