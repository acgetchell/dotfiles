---
name: rust-iter-control-flow
description: "Review Rust iterator and branching code when control flow, allocation, or readability is materially in scope."
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

Choose a loop or iterator pipeline by how clearly it expresses the operation.
Preserve traversal order, short-circuiting, side effects, ownership, and drop
behavior when transforming one into the other. Stateful coordinated updates and
complex early exits often read better as loops; simple transformations often
read better as iterator chains.

Check the decisions that can change behavior or cost:

- Intermediate collections, repeated clones, and repeated computations need a
  concrete purpose. Preserve snapshot semantics, borrowing constraints, and
  reuse when removing them; prefer streaming only when those contracts permit it.
- Iterator laziness must not suppress intended effects. Error collection and
  `try_fold` short-circuit; preserve required cleanup and failure order.
- `zip` truncates to the shorter input. Where equal lengths are a domain invariant,
  establish that proof before iteration rather than silently dropping values.
- `iter`, `iter_mut`, and `into_iter` should express the intended ownership. Check
  closure captures and `move` against task lifetimes and mutation needs.
- Callable bounds should require only the capability used: a one-shot caller can
  accept `FnOnce`; repeated mutation can require `FnMut`; shared callable access
  can require `Fn`. Do not strengthen a public bound merely for stylistic symmetry.
- Dynamic dispatch or a named helper can be appropriate for heterogeneity, code
  size, or reuse. Replace it only for a concrete clarity or cost benefit.
- Pattern matching should expose meaningful branches and preserve domain
  exhaustiveness. Avoid catch-alls that hide new closed-enum cases and unjustified
  `_ => unreachable!()`; use an intentional fallback for external non-exhaustive
  types.
- Prefer `if let`, `let else`, `matches!`, or slice patterns when they clarify the
  operation. Do not report an equivalent `match` or loop as a defect solely for
  using a different idiom.

## Results

Use the parent result contract when dispatched. Otherwise report concrete
findings with source locations, their effect on behavior, allocation,
exhaustiveness, or capture, and relevant validation. Separate optional readability
preferences from required corrections. A clean result needs no invented rewrite.
