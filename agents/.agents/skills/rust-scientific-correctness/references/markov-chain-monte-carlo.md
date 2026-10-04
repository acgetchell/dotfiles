# markov-chain-monte-carlo Scientific Correctness

Use this reference when applying `rust-scientific-correctness` to `markov-chain-monte-carlo` or related Metropolis-Hastings code. Always read applicable `AGENTS.md`, required reviewer guidance, and the scientific-basis assumptions relevant to the reviewed contracts. Current repository contracts override stale details here; report contradictions rather than silently choosing one.

## Select Background By Contract

Use the changed behavior and nearby dependencies, not just filenames, to choose background:

| Reviewed contract | Required background |
| --- | --- |
| Target weights, acceptance, proposal ratios, support, rollback, or delayed commit | Proposal validation (including `docs/VALIDATING_PROPOSALS.md` when present), the concrete proposal workflow, and its target/transition assumptions. |
| Snapshot, serialization, resume, cached target values, counters, or RNG continuation | Checkpoint and continuation documentation (including the relevant `src/lib.rs` sections), checkpoint validation, and state/RNG ownership. Load proposal validation if resume changes proposal state or transition identity. |
| Adaptation, warm-up, tuning, or update schedules | Adaptation and stationarity assumptions, freeze/update boundaries, and affected proposal or diagnostic contracts. |
| Pooled ranks, R-hat, ESS, MCSE, diagnostic exports, or timing | Diagnostic definitions, sample layout, ties, normalization, finite-sample and non-finite behavior, and reference-oracle assumptions. For timing, include the measured diagnostic workload and correctness checks outside the timed region. |
| Seeds, streams, parallel chains, chunking, reproducibility claims, or seeded fixtures | The promised reproducibility boundary and relevant RNG/stream contracts; add checkpoint guidance for resumed/chunked equivalence. |

A rank-only change does not by itself require proposal or checkpoint background.
A proposal-only change does not by itself require diagnostic or checkpoint
background. A checkpoint-only change requires continuation and reproducibility
context, but proposal validation is conditional on its dependencies. Read the
relevant sections even when unrelated contracts share the same file.

If the boundary is uncertain, trace callers and shared state/helpers and load the
additional contracts needed to resolve it. Missing or contradictory assumptions
require broader context or an explicit finding, never an unsupported exclusion.
Keep the complete scientific checklist and independent-evidence requirements;
record the reason for each additional background dependency.

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
