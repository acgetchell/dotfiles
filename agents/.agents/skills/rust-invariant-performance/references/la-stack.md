# la-stack Performance Invariants

Use this reference when applying `rust-invariant-performance` to the `la-stack`
crate or related linear-algebra kernels.

## Preserve

- Matrix/vector shape, dimension, stride, and storage-layout invariants.
- Stack-allocation or small-buffer guarantees promised by public types.
- Exact arithmetic, pivoting, determinant, solve, factorization, and conditioning
  semantics.
- Parse-don't-validate boundaries for dimensions, shapes, capacities, index
  ranges, finite scalars, and algorithm options.
- Typed errors for shape mismatch, singularity, rank deficiency, non-finite
  input, overflow, and unsupported dimensions.
- No-unsafe constraints when the crate forbids unsafe code.

## Hot Paths

- Matrix construction and shape conversion.
- Inner arithmetic loops, row/column iteration, dot products, reductions, and
  matrix multiplication.
- Decomposition, solve, determinant, inverse, rank, and exact-arithmetic
  kernels.
- Conversion between stack, heap, slice, array, and iterator representations.
- Repeated shape checks in operations that already received shape proof.

## Performance Review Checks

- Move raw dimension validation into shape/proof types, then let kernels accept
  those proofs.
- Avoid repeated allocation for temporary rows, columns, pivots, permutation
  vectors, or workspaces.
- Prefer access patterns that match storage layout and preserve cache locality.
- Check whether iterator abstractions optimize cleanly in tight loops; prefer
  clear slices or arrays when benchmarks show overhead.
- Avoid formatting, cloning matrices, or collecting intermediate vectors in
  arithmetic kernels.
- Distinguish exact-arithmetic cost from floating-point fast paths and benchmark
  both when relevant.

## Benchmarks to Prefer

- Representative matrix sizes near stack/heap transition boundaries.
- Shape-checked operation benchmarks for proof-carrying API changes.
- Exact arithmetic and pivot-heavy adversarial cases.
- Allocation-count benchmarks for temporary workspace changes.
- Regression benchmarks for determinant/solve/factorization kernels.

## Do Not Optimize Away

- Shape checks at raw public boundaries.
- Singular/rank-deficient/non-finite error distinctions.
- Pivoting or exactness needed for documented numerical behavior.
- Storage-layout promises exposed by public APIs.
