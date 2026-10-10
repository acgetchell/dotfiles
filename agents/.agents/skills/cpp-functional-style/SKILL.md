---
name: cpp-functional-style
description: "Design or review substantial C++ data-transformation pipelines for clear effects, safe views, and preserved semantics."
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

### State the transformation

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

### Model values and alternatives

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

### Choose the clearest control form

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

### Control ownership, borrowing, and laziness

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

### Callable and failure composition

For higher-order or fallible pipelines, read
[callable composition](references/callable-composition.md).

### Preserve semantics and performance

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
