---
name: rust-iter-control-flow
description: "Audit Rust iterator, closure, loop, and pattern-matching control flow for clarity, allocation discipline, and exhaustiveness. Use for collect versus try_fold or flat_map, intermediate allocations, closure capture and Fn traits, match, if-let, or let-else choices, slice patterns, and cases where an imperative loop is clearer."
---

# rust-iter-control-flow

Audit Rust iterator, closure, and pattern-matching idioms for clarity, allocation discipline, and exhaustiveness.

The point is not iterators-for-the-sake-of-iterators. It is choosing the construct that makes data flow and failure modes obvious, and that puts invariants in the type system rather than in comments.

## Scope

Focus on newly added or modified Rust code that:

- chains iterator adapters (`map`, `filter`, `flat_map`, `fold`, `scan`, `zip`, `chain`, etc.)
- collects into containers (`collect`, `collect::<Result<_, _>>`, `collect::<Vec<_>>`)
- uses closures with non-trivial capture
- uses `match`, `if let`, `let else`, `while let`, or `matches!`
- pattern-matches structs, enums, slices, references, or tuples
- mixes loops and iterator chains for the same data

### Scope Modes

Default mode:
- Audit newly added or modified iterator chains, closures, loops, and pattern matches.
- Ignore unrelated unchanged control flow unless it defines local style or invariants for the changed code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit iterator/control-flow idioms across Rust source, tests, examples, and benches.
- Prioritize findings by correctness/exhaustiveness risk, avoidable hot-path allocation, misleading closure capture, and control flow that hides invariants.
- Do not require fixing every style preference in one pass; report low-risk readability cleanup separately.

## Review goals

### 1. Iterator chains versus manual loops

Prefer iterator chains when they reveal data flow, especially for:

- single-pass transforms
- short-circuiting via `try_fold`/`collect::<Result<_, _>>()`
- composition of `filter`/`map`/`flat_map`
- pipelines that match the natural shape of the data

Prefer imperative loops when:

- multiple data structures must be updated together
- the body has early returns or `continue`s that fight the iterator
- the chain becomes harder to read than the loop

Flag:

- iterator chains that recompute the same value repeatedly
- chains that hide side effects inside `map` or `for_each`
- imperative loops that simply rebuild a `map`/`filter` pipeline awkwardly

### 2. Allocation discipline in chains

Check:

- intermediate `collect()` calls are necessary
- `collect::<Vec<_>>()` between adapters is justified
- `into_iter()` vs `iter()` vs `iter_mut()` matches ownership intent
- `Iterator::sum`/`product`/`min`/`max`/`count` is used instead of folding into a `Vec`
- `collect::<Result<_, _>>()` is used to short-circuit on error
- `Iterator::partition` is used instead of two filtering passes

Flag:

- repeated `clone()` inside `map` when references would do
- intermediate `Vec`s that only feed another adapter
- `to_vec().iter()` patterns
- `collect::<Vec<_>>().into_iter()` round-trips

### 3. Closure capture and clarity

Check:

- closures capture by reference unless they need ownership
- `move` is used intentionally, especially when passing to threads or futures
- complex closure bodies are extracted to named functions when reused or large
- error-prone captures of mutable state are scoped tightly
- `Fn`/`FnMut`/`FnOnce` bounds on public APIs match what the implementation actually requires

Flag:

- accidental capture of `&mut` that prevents iterator composition
- closures that hide non-trivial logic and should be named functions
- public APIs that require `FnMut` or `FnOnce` when `Fn` would suffice (or vice versa)
- `Box<dyn Fn>` where a generic parameter would be both faster and clearer

### 4. `match` versus `if let` versus `let else`

Use:

- `match` when several arms have meaningful behavior
- `if let` for one interesting branch
- `let else` for guard-style early returns that bind on the happy path
- `while let` for iteration that ends on a sentinel
- `matches!` for boolean predicates over patterns

Flag:

- `match` with one real arm and a noise arm where `if let` or `let else` is clearer
- nested `if let` chains that obscure flow
- `match` that returns `true`/`false` instead of `matches!`
- early-return logic that destructures awkwardly without `let else`

### 5. Exhaustiveness and refutability

Check:

- `match` is exhaustive without a catch-all unless the catch-all is meaningful
- new enum variants force compile errors instead of silently matching `_`
- slice patterns (`[]`, `[_]`, `[head, tail @ ..]`) are used where they clarify shape
- `..` in struct patterns is intentional, not noise
- `#[non_exhaustive]` types are matched with explicit awareness of the constraint

Flag:

- `_ => unreachable!()` arms that should be exhaustive matches
- catch-alls that hide future variants
- non-exhaustive matching on `#[non_exhaustive]` types without an intentional fallback

### 6. Bindings and shape

Check:

- `@` bindings clarify intent when both the value and the structure are needed
- nested patterns are not deeper than they need to be
- references and `ref`/`ref mut` bindings are minimized in favor of pattern ergonomics

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Concrete idiomatic improvements with file/function references
- For each, state whether the issue is clarity, allocation, exhaustiveness, or capture

### Required Fixes
- Iterator chain restructuring
- Loop/iterator swaps
- Pattern-matching simplifications
- Exhaustiveness corrections

### Optional Improvements
- Stylistic or readability suggestions that do not change semantics
