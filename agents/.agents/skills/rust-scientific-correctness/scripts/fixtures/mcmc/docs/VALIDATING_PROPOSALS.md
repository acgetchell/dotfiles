# Proposal Validation

For a proposed transition from x to y, use the Metropolis-Hastings ratio
`pi(y) q(x|y) / (pi(x) q(y|x))`. `log_forward` is `ln q(y|x)` and `log_reverse`
is `ln q(x|y)`. The function returns the log acceptance probability capped at
zero. This fixture accepts finite log weights and finite log probabilities only.
For `src/proposal.rs`, no mutable state, delayed commit, adaptation, checkpoint,
or RNG contract is involved. Validate asymmetry with independently enumerated transition
probabilities, including self-loops.

The separate `src/proposal_state.rs` helper defines an independent proposal on
states 0 and 1: `probability_one` is the probability of proposing 1, regardless
of the current state. Its domain is strictly between 0 and 1, and the target is
uniform. Use the actual saved parameter in both forward and reverse proposal
probabilities. Its default is only for new chains; checkpoints preserve the
chosen parameter. This fixed kernel has no adaptation.
