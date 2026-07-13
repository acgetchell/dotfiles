# markov-chain-monte-carlo Scientific Correctness

Use this reference when applying `rust-scientific-correctness` to `markov-chain-monte-carlo` or related Metropolis-Hastings code. Read the repository's `AGENTS.md`, scientific basis, proposal validation, checkpoint, and reviewer guidance first; they override stale details here.

## Scientific Contracts

- Treat `Target<S>` as an unnormalized natural-log weight and preserve the documented Metropolis-Hastings acceptance ratio for the concrete sampled transition.
- Keep model, bias, umbrella, and auxiliary-energy terms in the target. Keep proposal asymmetry in the proposal ratio, including normalized move-family probabilities or their state-dependent normalizers, valid-site multiplicities, support restrictions, densities, and Jacobian factors when applicable.
- Preserve the distinct by-value, rollback-safe in-place, and delayed-commit proposal contracts. Rejection or proposal failure must not leave a partially mutated state, and a delayed plan must identify the transition it scores.
- Preserve log-space non-finite behavior, self-loop semantics, counters, cached target values, and checkpoint revalidation.
- Distinguish crate-owned transition mechanics and diagnostics from model-owned irreducibility, aperiodicity, recurrence, mixing, convergence, and observable interpretation.
- If adaptation is introduced or reviewed, treat it as part of the scientific kernel and verify that its warm-up and update rules preserve the claimed stationary or asymptotic behavior.

## Independent Evidence

- For small finite models, independently enumerate the state space and transition matrix, including self-loops; check row sums, target invariance, and detailed balance when reversibility is claimed.
- Derive proposal probabilities from the sampling process rather than reusing the production proposal-ratio method.
- Do not infer transition identity from equal target log weights; a score-only post-commit comparison can prove cache or score consistency without proving that the scored and committed states are the same.
- Compare long-run observables with analytical or independently computed distributions using uncertainty estimates that account for autocorrelation.
- Verify rollback against an exact state snapshot. Agreement across proposal workflows is parity evidence, not an independent oracle.
- For continuous proposals, check the proposal density or a justified distributional property rather than relying on exact endpoint hits.

## Adversarial Regimes

- Zero target mass, zero reverse probability, empty proposal sets, self-loops, extreme finite log-weight differences, and non-finite target or proposal values.
- Highly asymmetric, reducible, disconnected, periodic, slowly mixing, and strongly autocorrelated kernels.
- Failures during proposal, scoring, commit, rollback, checkpoint resume, burn-in, thinning, and chunk boundaries.
- Mutable proposals that fail after partial work and delayed workflows whose scored state differs from the committed state.

## Reproducibility And Claim Checks

- Compare chunked and uninterrupted seeded runs when the API promises equivalent continuation, including state, counters, cached values, and RNG ownership.
- Require explicitly independent streams for parallel chains; equal seeds establish repeatability, not independence.
- State sample count, tolerance, false-positive risk, autocorrelation treatment, and convergence assumptions for statistical assertions.
- Do not present empirical detailed-balance diagnostics as proof of ergodicity, convergence, adequate mixing, or model validity.
- Use the repository's documented reproducibility boundary. Do not infer cross-version, cross-toolchain, cross-architecture, or parallel bit-for-bit stability from same-build seeded repeatability.
