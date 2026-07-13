# delaunay Scientific Correctness

Use this reference when applying `rust-scientific-correctness` to `delaunay` or closely related computational-geometry code. Read `AGENTS.md`, current limitations, and the geometry, topology, invariant, and validation documentation first; they override stale details here.

## Scientific Contracts

- Preserve the validation hierarchy as separate claims: element validity, combinatorial consistency, intrinsic PL topology, valid realization, and geometry-specific predicates. Passing one layer does not establish a higher layer.
- Keep intrinsic simplex dimension, ambient embedding dimension, and predicate dimension distinct, especially for toroidal and spherical backends.
- Preserve robust-predicate sign behavior, proved floating-point filters, exact fallback, and deterministic Simulation of Simplicity handling for degenerate inputs. Keep the exact unperturbed sign, explicit geometric zero, SoS-resolved perturbed sign, and typed unresolved-degeneracy outcome distinct.
- Reject non-finite public point inputs according to the active boundary contract. Do not confuse conservative low-level classification of an unresolvable non-finite intermediate with acceptance of non-finite geometry.
- Preserve adjacency, facet multiplicity, link, manifold, orientability, connectedness, Euler-characteristic, realization, and Delaunay invariants at the layer that owns each one. Account for documented periodic-identification cases rather than treating every self-neighbor as a boundary defect.
- Treat Euclidean, periodic toroidal, canonicalized-coordinate toroidal, and spherical constructions as different scientific models with backend-specific realization and predicate contracts. Coordinate canonicalization alone is not a periodic quotient.
- Keep mutation and repair failure-atomic. A successful edit must preserve the claimed validation layers; bounded exhaustion remains typed non-convergence rather than silent partial success.

## Independent Evidence

- Check orientation and in-sphere signs with an exact determinant formulation independent of the production predicate fallback, preserving geometric-zero versus SoS-resolved semantics.
- For small nondegenerate point sets, use an independent empty-sphere check over every relevant simplex/point pair whose arithmetic does not wrap the same production determinant path.
- Validate topology with analytically known complexes and independently assembled incidence, link, manifold, and Euler calculations rather than only production report helpers.
- Validate realization with exact or independently derived orientation and intersection fixtures, including valid shared-face contact and invalid crossings.
- Check local moves through link and f-vector invariants. When a concrete inverse exists, require the documented round-trip identity, including vertex and top-dimensional incidence semantics rather than only recovered counts.
- On matching models and general-position input, compare canonicalized results across insertion orders or an independent implementation. Treat external agreement as supplementary evidence. On degenerate input, compare promised invariants and deterministic tie-breaking rather than assuming a unique simplex set.

## Adversarial Regimes

- Collinear, coplanar, cocircular, cospherical, duplicate, nearly degenerate, mixed-scale, extreme-magnitude, and non-finite coordinates.
- Insertions or edits on existing vertices, edges, ridges, facets, and predicate boundaries.
- Broken reciprocity, overshared facets, inconsistent orientation, disconnected complexes, invalid links, overlaps, and incorrect Euler characteristic.
- Toroidal seam and periodic-image cases, plus spherical antipodal, near-antipodal, and empty-cap boundaries within the documented backend scope.

## Claims And Benchmark Validity

- Qualify an “exact predicate” claim by predicate, supported dimension, kernel, and fallback semantics.
- Do not claim that intrinsic topology establishes a valid realization, or that realization establishes Delaunay optimality.
- Compare construction or validation performance only with the same coordinate model, topology guarantee, predicate kernel, validation level, and supported dimension.
- Reject timing evidence when the measured result fails any validation layer included in the claim. A repair benchmark may intentionally start damaged only when setup proves the intended defect and postconditions prove the required repaired layers.
