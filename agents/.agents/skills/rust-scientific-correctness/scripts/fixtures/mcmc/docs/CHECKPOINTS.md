# Checkpoint Contracts

In `src/checkpoint.rs`, the snapshot contains the original seed and the current generator state.
Resume must continue from that current state; the original seed is provenance.
The toy generator has recurrence `s_next = 3 * s + 1` with wrapping u64 arithmetic.
It exists only to make continuation independently calculable, not as a proposed
statistical RNG. No target, proposal, adaptation, or diagnostics are serialized.
Read the reproducibility boundary when judging continuation claims.

In `src/checkpoint_proposal.rs`, the snapshot additionally contains a fixed
proposal parameter owned by `src/proposal_state.rs`. Resume must preserve both
the generator state and that parameter. The proposal contract defines its effect
on transition probabilities; restoring RNG state alone cannot preserve the
saved transition kernel. This parameter is not adapted during sampling.
