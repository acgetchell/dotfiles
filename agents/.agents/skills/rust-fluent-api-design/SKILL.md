---
name: rust-fluent-api-design
description: "Review Rust public APIs for fluent, staged workflow ergonomics without forcing every API into a chain. Use when users ask about fluent APIs, method chaining, builders, proposals, transactions, guards, configuration workflows, terminal mutation methods, public examples, or whether to keep/remove duplicate non-fluent Rust functions; coordinate with parse-don't-validate when a chain should carry validation evidence through proof-bearing types."
---

# rust-fluent-api-design

Review Rust APIs for fluent workflow ergonomics: staged chains that read in domain order, make the happy path obvious, and preserve explicit fallibility and mutation boundaries.

This skill is a review lens, not a blanket mandate. Recommend fluent APIs when they improve correctness, orthogonality, or caller ergonomics; avoid forcing ordinary accessors, queries, primitive helpers, or one-step operations into chains.

## Scope

Focus on changed or proposed Rust public APIs that:

- model staged workflows such as builders, proposals, transactions, guards, validators, commands, or reports
- parse raw input into an intermediate object before a dry-run, commit, execute, or build step
- expose both fluent and non-fluent forms of the same operation
- appear in README examples, doctests, integration tests, examples, or benchmarks
- use closures or iterator chains to hide side effects that would be clearer as a named fluent step

Ignore purely internal helper APIs unless they shape the public workflow or duplicate public surface.

## Review Principles

### Prefer Fluent Stages When They Match the Domain

Good fluent APIs make the valid sequence hard to miss:

```rust
let result = owner
    .propose_change(raw_request)?
    .can_attempt_on(&owner)?;

let result = owner
    .propose_change(raw_request)?
    .attempt_on(&mut owner)?;
```

Prefer this shape when the sequence is meaningful:

- configure -> build
- raw request -> proposal -> dry-run/commit
- begin transaction -> mutate -> commit/rollback
- query builder -> execute
- parse options -> run

The chain should read in domain order and keep every fallible stage visible with `?`.

### Coordinate With Parse-Don't-Validate

When a stage validates raw input, the next stage should consume or borrow a proof-bearing value rather than reaccepting raw values.

Prefer:

```rust
let proposal = owner.propose_move(raw_move)?;
proposal.attempt_on(&mut owner)?;
```

over:

```rust
owner.attempt_move(raw_move)?;
```

when `raw_move` contains handles, indexes, dimensions, topology IDs, numeric constraints, or other invariant-bearing input.

Do not recommend fluent chaining that discards validation evidence or stores invalid state. Use `rust-parse-dont-validate` for deeper invariant-boundary review.

### Keep Mutating Terminal Operations Explicit

Fluent terminal methods that mutate should be named as commands:

- `attempt_on`
- `commit`
- `apply_to`
- `execute`
- `build`
- `finish`

Avoid hiding mutation inside `map`, `and_then`, `filter`, `inspect`, or `for_each` in public samples. A side-effecting terminal method should be visually obvious.

### Preserve Orthogonality

Do not require fluent style for every method.

Keep non-fluent APIs when they provide real value:

- trait dispatch or object-safe implementation hooks
- primitive/expert layer operations
- one-step operations with no meaningful intermediate state
- accessors, iterators, queries, and validation reports
- standard trait implementations where fluent naming is not available

Question non-fluent duplicates when they merely restate the fluent terminal method and broaden public surface without adding capability.

### Public Samples Teach The Canonical Path

README examples, doctests, integration-style tests, examples, and benchmarks should show the intended ergonomic workflow. If both low-level and fluent APIs remain public, public samples should normally use the fluent path and reserve low-level calls for primitive-layer docs or focused tests.

Avoid adding local helpers whose whole purpose is to hide the fluent workflow, such as a `build_default(...)` wrapper around `Builder::new(...).option(...).build()`. Fixture helpers are fine when they encode real domain setup, expected structures, generated data, or repeated assertions. Thin wrappers over the canonical chain are a design-feedback smell: they make tests and samples less representative, and they can mask that the public fluent API is too noisy, poorly ordered, or missing a domain-named stage. Prefer writing the chain directly in API-facing tests and samples; if that feels repetitive or ugly, improve the fluent API rather than hiding it.

## Review Checklist

- Does the chain read in the same order a user thinks about the workflow?
- Does each stage either return a useful proof-bearing value or perform a clear terminal action?
- Is mutation visually explicit at the terminal method?
- Are errors typed and propagated with `?`, not hidden in closure control flow?
- Does the chain avoid unnecessary clones or allocations?
- Are intermediate types named for what they prove, such as `Proposal`, `Builder`, `Transaction`, `Guard`, `Plan`, or `Prepared*`?
- Are infallible methods genuinely infallible for all representable inputs?
- Does a non-fluent public method add orthogonal capability, or is it redundant surface?
- Do public examples and doctests use the ergonomic canonical path?

## Suggested Fixes

When recommending changes, be specific about the API shape:

- add a fluent method to the proof-bearing intermediate type
- rename the raw boundary so it reads naturally in a chain
- make the mutating terminal method consume the intermediate value when reuse would be stale
- keep a lower-level trait method private, sealed, hidden, or documented as an implementation hook when possible
- update public samples to teach the fluent path
- add tests that prove rejected terminal operations have no unwanted side effects

Avoid broad rewrites. Prefer small, staged API improvements that preserve correctness and make the workflow easier to copy.

## Output Format

### Scope
- State whether the review covers changed APIs, a specific public workflow, or a broader API baseline.

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Ordered by impact.
- Include file and line references.
- Explain whether the issue is workflow order, hidden mutation, redundant public surface, lost validation evidence, or public-sample ergonomics.

### Suggested Fixes
- Give concrete method/type names and the intended chain shape.
- Name tests or examples that should change.

### Optional Improvements
- List non-blocking ergonomic polish separately from correctness or API-surface concerns.
