# delaunay Production Review Notes

Use this reference when applying `rust-production-review` to the `delaunay`
crate or closely related computational-geometry code.

## Validation Architecture

- Preserve the validation hierarchy as separate responsibilities:
  - Level 1: local object validity.
  - Level 2: combinatorial consistency.
  - Level 3: intrinsic PL topology.
  - Level 4: embedding validity.
  - Level 5: geometric predicates.
- Geometry backends such as Euclidean, toroidal, and spherical support should
  specialize embedding and predicate layers, not redefine intrinsic topology.
- Delaunay or other geometric predicates must not substitute for lower-level
  topology or embedding validation.
- Keep intrinsic dimension and ambient dimension distinct. For example,
  spherical `S^D` lives in `R^(D + 1)`, but the abstract simplex dimension
  remains `D`.
- Public fast-fail wrappers such as `is_valid_*` should delegate to canonical
  `validate_*` implementations instead of duplicating logic that can drift.

## Review Focus

- Check that topology, embedding, and predicate errors preserve layer-specific
  typed context for callers and tests.
- Check new geometry backends against degenerate, malformed, duplicate, empty,
  wrong-dimension, and wrong-radius inputs.
- Check that helper extraction makes invariant-preserving steps clearer without
  widening visibility or hiding failure context.
