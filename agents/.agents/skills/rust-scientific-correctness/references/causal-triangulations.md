# causal-triangulations Scientific Correctness

Use this reference when applying `rust-scientific-correctness` to `causal-triangulations` or related CDT simulation code. Read the repository's `AGENTS.md`, scientific basis, foliation, move, Metropolis, and limitation documentation first; they override stale details here.

## Scientific Contracts

- Review the currently documented 1+1-dimensional model without generalizing its identities or guarantees to future 2+1 or 3+1 work.
- Preserve topology, boundaries, slice structure, foliation labels, adjacent-slice causality, strict Up/Down simplex classification, and toroidal spatial/time wrap-around.
- Preserve the documented count changes of local `(2,2)`/`EdgeFlip`, `(1,3)`, and `(3,1)` moves, and require planned and reported action deltas to agree with full recomputation.
- Preserve proposal-before-mutation ordering, the actual proposal-site universe, inverse-family probability corrections, self-loop handling, and failure-atomic rollback.
- Treat the Delaunay backend as an initialization and checked-edit substrate rather than a sampled physical constraint; evolved CDT states need not retain the empty-circumsphere property unless the model explicitly changes.
- Treat current simulations as the documented grand-canonical, unfixed-volume ensemble. Expected volume drift is not itself an invariant failure.
- Apply closed-torus count identities and critical-coupling conversions only under their documented closed 1+1 convention; open strips have boundary corrections.

## Independent Evidence

- Independently traverse vertices, edges, faces, labels, and slice subgraphs to check counts, Euler characteristic, connectivity, causality, and strict simplex classification.
- Compare each move's recorded count and planned or reported action delta with full recomputation from the resulting triangulation.
- Apply a move and valid inverse on small fixtures and compare canonical combinatorial state, topology, foliation, action, and cached summaries.
- On enumerable small triangulations, independently construct proposal-site sets and transition probabilities; verify multiplicities, self-loops, target invariance, and detailed balance where claimed.
- Compare local eligibility and invariant checks with independent full-state validation across repeated mixed moves.

## Adversarial Regimes

- Minimum legal slices and volumes, nonuniform profiles, open boundaries, and spatial or temporal toroidal seams.
- Sites editable by the geometry backend but invalid under topology, foliation, causality, or simplex-classification constraints.
- Missing labels, stale proposal or invariant caches, zero reverse-site counts, empty move families, and failure after partial mutation or refresh.
- Extreme finite couplings or temperatures and long unfixed-volume runs near shrinkage or growth regimes.

## Reproducibility And Claim Checks

- Compare chunked continuation with uninterrupted seeded runs when checkpoints preserve triangulation, sampler state, proposal and acceptance RNGs, counters, and action configuration.
- Keep no-site self-loops, invalid-site rejections, Metropolis rejections, hard failures, and accepted transitions distinct in traces and claims.
- Do not infer detailed balance, ergodicity, mixing, continuum scaling, or physical validity from one seeded valid run.
- State topology, boundary conditions, couplings, temperature, move weights, seed policy, sweep definition, and fixed- versus unfixed-volume semantics in scientific comparisons.
- Do not describe the evolved ensemble as Delaunay or fixed-volume unless those constraints are explicitly added to the sampled model.
