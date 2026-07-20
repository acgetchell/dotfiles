# CDT++ Scientific and Topology Contracts

Load this reference when CDT++ scope touches CGAL handles or triangulations, topology moves, numerical predicates, causal structure, stochastic proposals, or simulation behavior.

## Lifetime and Mutation

- Treat CGAL handles, iterators, circulators, and references as invalidation-sensitive across insertion, removal, flips, swaps, copies, moves, and triangulation replacement.
- Verify guarantees from the installed CGAL version or current official documentation rather than assuming stability.
- Ensure rejected mutations leave the manifold unchanged and successful mutations refresh every dependent handle, adjacency relation, cache, and index.

## Move Invariants

For 2-to-3, 3-to-2, 4-to-4, 2-to-6, and 6-to-2 moves, verify:

- applicability and boundary preconditions
- exact simplex-count deltas
- causal foliation and orientation
- reciprocal adjacency and manifold validity
- failure atomicity and inverse-operation behavior

Use independent counts, canonical snapshots, incidence properties, or trusted CGAL predicates rather than only production validity helpers.

## Numerical and Stochastic Behavior

- Keep units, orientation conventions, tolerance policy, and degenerate-input behavior explicit.
- Keep RNG ownership at the simulation, test, or benchmark level; pass engines by reference and keep distributions separate.
- Preserve deterministic replay and report failing seeds.
- Check proposal and acceptance probabilities independently, including normalization and boundary cases.
