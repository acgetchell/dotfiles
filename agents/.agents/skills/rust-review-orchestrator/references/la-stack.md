# la-stack Routing Notes

Use this reference when `rust-review-orchestrator` is running in the `la-stack`
crate or closely related linear-algebra code.

## Repository Guidance

- Read local repository instructions before editing, especially `AGENTS.md`,
  development command docs, and benchmark guidance when present.
- Prefer documented project validators. If none exist, start with the generic
  Cargo fallbacks in `check-routing.md`.
- When changes affect matrix kernels, decomposition, solve, determinant,
  factorization, exact arithmetic, or storage layout, pair correctness tests with
  the narrowest available benchmark or allocation check.

## Review Emphasis

- Treat mathematical correctness as the first invariant: dimensions, shapes,
  strides, storage layout, pivoting, singularity/rank-deficiency behavior,
  finite-scalar handling, exact arithmetic, and conditioning semantics must stay
  intact.
- Treat stack allocation and small-buffer guarantees as both API and performance
  constraints. Do not "optimize" by silently moving promised stack-resident work
  to the heap.
- Prefer proof-carrying shapes, dimensions, capacities, and algorithm options so
  hot kernels can avoid repeated raw validation without losing safety.
- Look for allocation and data-movement regressions around row/column iteration,
  dot products, reductions, matrix multiplication, temporary workspaces, and
  stack/heap transition boundaries.
- Preserve typed errors for shape mismatch, singularity, rank deficiency,
  non-finite input, overflow, and unsupported dimensions.

