# la-stack Scientific Correctness

Use this reference when applying `rust-scientific-correctness` to `la-stack` or closely related fixed-size linear-algebra code. Read the repository's `AGENTS.md`, limitations, API documentation, and benchmark guidance first; they override stale details here.

## Scientific Contracts

- Preserve the const-generic fixed-dimension model and stack-oriented storage contract. Treat D=2 through D=5 as the current required test matrix for dimension-generic behavior, not the crate's complete API domain.
- Keep `det_direct` within its documented D=0 through D=4 domain. `Matrix::det` uses a documented numerical path outside that domain; do not label its fallback as direct evaluation or exact proof of zero.
- Treat `det_errbound` as potentially available only through D=4. It may return `None` for underflow-sensitive computations even within that range; apply its guarantee only under the documented intermediate-value assumptions.
- Preserve exact determinant and solve results as rational values of the inputs' exact binary64 representations, not their intended decimal spellings. Strict exact-to-`f64` conversion rejects required rounding, while explicitly rounded conversion opts into rounding; neither silently returns a non-finite value.
- Preserve typed non-finite origin/location, singularity, tolerance, factorization, arithmetic-operation, and representability context. Parse raw tolerances through the crate's validated tolerance boundary.
- Treat LU partial-pivoting and LDLT symmetry/positive-semidefinite preconditions as algorithm contracts. Singular PSD inputs need not produce a usable LDLT factorization, and indefinite or zero-with-coupling failures remain distinct from numerical singularity.

## Independent Evidence

- Check determinants with a generic exact permutation expansion or rational elimination that does not reuse whichever specialized expansion or Bareiss helper is active in production.
- Check approximate solves against exact or higher-precision solutions and condition-aware residual or backward-error evidence; a small residual alone is insufficient for an ill-conditioned system.
- Whenever `det_errbound` returns `Some(bound)`, compare with an independently computed exact determinant of the same binary64 inputs and verify the stated inequality.
- Check specialized and general determinant paths on their shared domain, and check filtered exact signs against an independent exact sign oracle.
- Exercise all required dimensions without inventing an unsupported D=5 direct-determinant or direct-error-bound case.

## Adversarial Regimes

- Exactly singular, rank-deficient, near-singular, pivot-requiring, Hilbert-style, and mixed-scale matrices.
- Extreme finite magnitudes, cancellation, overflow-prone intermediates, subnormals, signed zero, NaN, and infinities.
- Positive definite, semidefinite, and deliberately indefinite inputs at LDLT contract boundaries.
- Exact-to-`f64` values immediately around rounding, subnormal, maximum-finite, and non-finite conversion boundaries.

## Claims And Benchmark Validity

- Never report D≥5 `det_direct` returning `Ok(None)` as determinant performance. An unsupported-dispatch or expected-error workload may be benchmarked only under an explicit label that does not present it as a determinant result.
- Treat `det_errbound(None)` as absence of a certified bound for that case, not as a zero bound or a determinant result.
- Distinguish floating, exact, strict-conversion, and rounded-conversion workloads and guarantees.
- Compare with nalgebra, faer, or another implementation only when the operation, precision, validation assumptions, and supported dimensions are equivalent.
- Require benchmark fixtures to pass the relevant independent correctness checks before treating their timings as evidence.
