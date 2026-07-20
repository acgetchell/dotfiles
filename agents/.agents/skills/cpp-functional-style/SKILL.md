---
name: cpp-functional-style
description: "Design, write, refactor, and review modern C++23 around explicit data transformations, value semantics, immutable interfaces, standard algorithms and ranges, higher-order functions, algebraic result types, and controlled effects. Use when work materially involves pipelines, range/view lifetimes, folds, callbacks, optional/expected/variant composition, or replacing difficult mutating workflows with value-returning state transitions; do not trigger for incidental lambdas or ranges."
---

# C++ Functional Style

Write modern C++ around clear transformations and explicit effects. Use functional
techniques where they improve correctness and composition while retaining ordinary
loops, local mutation, and value-oriented classes when those are clearer or faster.

## Ground Rules

- Read repository-local instructions and establish the supported C++ standard,
  compilers, and standard libraries before choosing facilities.
- Treat functional style as a design tool, not a quota for ranges, lambdas, or
  point-free expressions.
- Preserve observable behavior unless the user explicitly requests a semantic
  change.
- When asked only to explain or review, remain read-only. When asked to implement
  or refactor, make the smallest coherent change and validate it.
- Keep lifetime, error, numerical, allocation, and concurrency costs visible.
  Concise syntax is not evidence that a transformation is safe or cheap.

## Workflow

### 1. State the transformation

Describe the code as inputs, outputs, invariants, and effects before selecting
syntax. Identify:

- the values that enter and leave each stage
- which stages are total and which can fail
- ordering, multiplicity, and stability requirements
- I/O, logging, clocks, randomness, shared state, callbacks, and allocation
- ownership and lifetime of every range, view, callable, and returned value

Separate a pure computational core from an effectful shell when it creates a
clear boundary. Pass changing dependencies such as clocks or random engines
explicitly when deterministic control matters.

For fallible state changes, prefer a value-returning interface such as
`State const& -> std::expected<State, E>`: construct a complete candidate
privately, then publish it at an explicit commit boundary. Local mutation inside
an unobservable candidate is compatible with functional design. Avoid copying
large state blindly; use moves, ownership transfer, or a transaction-style
implementation where appropriate.

### 2. Model values and alternatives

Prefer value semantics and types that express the domain:

- small immutable-by-interface value objects for stable domain facts
- `enum class` for finite categories
- `std::optional<T>` for genuine absence
- `std::variant<...>` for mutually exclusive states with different payloads
- `std::expected<T, E>` under a supported C++23 contract, or the repository's
  established result type, for expected fallible composition
- ordinary named structs when several values travel together

Use `const` to communicate stable bindings and interfaces, but do not scatter it
onto locals when it obstructs moves or adds no useful constraint. Avoid getters
that expose mutable storage merely to enable a pipeline.

### 3. Choose the clearest control form

Prefer a standard algorithm or ranges pipeline when it names the operation and
keeps the data flow linear. Common fits include:

- `transform` for one-to-one mapping
- `filter` for selection
- `find`, `any_of`, `all_of`, or `none_of` for search and predicates
- `std::ranges::fold_left`, where supported, or `std::accumulate` for a
  left-to-right reduction with one explicit accumulator; preserve evaluation
  order when ordering or floating-point association matters
- `zip`, where available under the declared standard-library contract, for
  lockstep traversal with deliberate truncation or size checks

Prefer an ordinary loop when it makes any of these clearer:

- several outputs or data structures change together
- short-circuiting and cleanup have multiple branches
- mutation is the algorithm rather than incidental bookkeeping
- a pipeline would hide indexing, iterator invalidation, or failure atomicity
- named intermediate state explains the domain better than nested adaptors

Do not use `map`-like operations for side effects. Keep effects in a loop,
`for_each`, or a named boundary whose purpose is explicit.

### 4. Control ownership, borrowing, and laziness

Ranges and views are often lazy and non-owning. Verify:

- no returned view, iterator, `std::span`, or `std::string_view` refers to a local
  object or expired temporary
- the source range outlives every lazy consumer
- lambda captures outlive deferred execution
- mutation cannot invalidate iterators while a view pipeline still uses them
- a one-shot input range is not accidentally traversed twice
- caching a view does not silently cache references into replaceable storage

Prefer an owning result when the lifetime contract would otherwise be subtle.
Materialize once at a deliberate boundary rather than inserting multiple
intermediate containers between adaptors.

### 5. Compose callables deliberately

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

### 6. Keep failure in the data flow

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

### 7. Preserve semantics and performance

Check behavior hidden by compact expressions:

- evaluation order and short-circuiting
- repeated computation in lazy views
- intermediate allocation and accidental copies
- `std::accumulate` versus reorderable reductions such as `std::reduce`
- floating-point reassociation and reproducibility
- stable ordering, duplicate handling, and iterator category requirements
- side effects under parallel execution policies

Do not assume a functional-looking rewrite is faster. Measure non-obvious hot
path changes and retain a loop when it provides clearer control over allocation,
vectorization, or cache behavior.

## Validation

Run the narrowest repository-supported build, formatting, static-analysis, and
test commands that exercise the change. Add or strengthen tests for:

- empty, singleton, boundary, and invalid inputs
- ordering and duplicate behavior
- every fallible stage and short-circuit path
- successful transitions returning a complete invariant-satisfying value
- rejected transitions leaving the source value unchanged
- deterministic behavior with injected clocks or random engines
- lifetime-sensitive view use under ASan/UBSan when relevant
- equivalence to the prior implementation for semantics-preserving refactors

For reviews, report each finding with the transformation and effect contract,
its observable risk, the smallest clearer design, and validation evidence. For
implementation work, summarize changed files, semantic decisions, validators,
and any deliberately retained imperative code.
