# markov-chain-monte-carlo Performance Invariants

Use this reference when applying `rust-invariant-performance` to the
`markov-chain-monte-carlo` crate or related stochastic simulation code.

## Preserve

- Target distribution, stationary distribution, detailed balance, reversibility,
  or documented non-reversible semantics.
- Proposal, acceptance, rejection, adaptation, burn-in, thinning, and sample-count
  invariants.
- RNG reproducibility, stream independence, seed handling, and deterministic test
  behavior.
- Parse-don't-validate boundaries for probabilities, log probabilities, finite
  actions, positive sample counts, burn-in lengths, thinning intervals, proposal
  parameters, and chain configuration.
- Typed errors for invalid probabilities, non-finite scores, invalid schedules,
  invalid dimensions, exhausted budgets, and sampler configuration failures.
- Diagnostics needed to detect invalid states, divergence, poor acceptance, or
  reproducibility regressions.

## Hot Paths

- Per-step proposal generation, scoring, acceptance tests, and state updates.
- Log-density evaluation and repeated target/proposal calculations.
- Sample storage, trace accumulation, diagnostics, and thinning logic.
- Adaptation schedules and warm-up loops.
- Random number generation and distribution sampling.

## Performance Review Checks

- Validate sampler configuration once, then pass proof-bearing config into the
  stepping kernel.
- Keep accepted/rejected/no-proposal state as an enum or typed telemetry rather
  than parallel booleans/options.
- Avoid allocating per step for proposals, diagnostics, errors, or trace records.
- Do not change RNG call counts, stream order, or acceptance ordering unless the
  public stochastic contract is intentionally changed.
- Cache target or proposal values only when invalidation and detailed-balance
  implications are explicit.
- Check that diagnostics are sampled, gated, or accumulated without formatting in
  the per-step hot path.

## Benchmarks to Prefer

- Fixed-seed step throughput for representative models.
- Allocation counts per step and per retained sample.
- Benchmarks separating scoring cost from sampler overhead.
- Long-chain benchmarks that include burn-in/thinning/reporting behavior.
- Statistical regression tests or diagnostics for changes affecting transition
  semantics.

## Do Not Optimize Away

- RNG reproducibility and stream independence.
- Typed invalid-probability/non-finite-score errors.
- Acceptance/rejection semantics or diagnostic state needed to detect sampler
  failure.
- Tests that guard target-distribution or detailed-balance behavior.
