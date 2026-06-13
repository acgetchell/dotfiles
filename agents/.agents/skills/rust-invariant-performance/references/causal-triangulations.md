# causal-triangulations Performance Invariants

Use this reference when applying `rust-invariant-performance` to the
`causal-triangulations` crate or related triangulation Monte Carlo code.

## Preserve

- Manifold, topology, causal, slice, boundary, adjacency, and move-validity
  invariants.
- Detailed balance, proposal symmetry/asymmetry accounting, acceptance semantics,
  and stationary distribution when moves are sampled probabilistically.
- Parse-don't-validate boundaries for dimensions, slice counts, volumes, simplex
  types, move kinds, coupling constants, budgets, and triangulation state.
- Typed errors for invalid moves, invalid topology, non-convergence, invalid
  parameters, and exhausted work budgets.
- Reproducible seeded simulations and deterministic validation fixtures.

## Hot Paths

- Local move proposal, eligibility checks, application, rollback, and acceptance.
- Neighbor, boundary, simplex, and slice traversal.
- Action/weight calculation and delta-action updates.
- Local and global validation after moves.
- Monte Carlo sweep loops, diagnostics, and trace/sample output.

## Performance Review Checks

- Prefer local proof types for move eligibility so applying a move does not
  re-check unrelated global invariants.
- Validate raw simulation configuration once, then pass typed parameters and
  budgets into sweeps.
- Avoid cloning entire triangulations for local move attempts unless rollback
  cannot be represented locally.
- Keep adjacency, slice, boundary, and volume summaries coherent when caching;
  stale cache bugs are correctness failures.
- Do not skip validation layers after mutation unless the move proof guarantees
  the preserved invariant and tests cover it.
- Keep logging/diagnostic formatting outside per-move measured loops.

## Benchmarks to Prefer

- Move eligibility and local application benchmarks by move kind.
- Sweep throughput with fixed seeds and representative triangulation sizes.
- Validation cost benchmarks for local-vs-global checks.
- Allocation-count benchmarks for move application and rollback.
- Statistical or detailed-balance regression tests for transition changes.

## Do Not Optimize Away

- Move validity checks that protect topology or causal structure.
- Rollback/atomicity guarantees after rejected or failed moves.
- Typed non-convergence and exhausted-budget errors.
- Seeded reproducibility for simulations and tests.
